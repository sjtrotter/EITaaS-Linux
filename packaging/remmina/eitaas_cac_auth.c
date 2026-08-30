// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 Stephen Trotter

#include "eitaas_cac_auth.h"

#include <gtk/gtk.h>
#include <string.h>

#ifndef PKCS11_TOOL
#define PKCS11_TOOL "/usr/bin/p11tool"
#endif
#define PKCS11_TIMEOUT_SECONDS 15
#define PKCS11_MAX_OUTPUT (256 * 1024)
#define PKCS11_MAX_URI 4096
#define PKCS11_MAX_LABEL 256
#define PKCS11_MAX_TOKENS 16
#define PKCS11_MAX_CERTIFICATES 64
#define CERTAUTH_HOST_PREFIX "certauth."
/* p11-kit's System/Default Trust tokens never hold a client certificate. */
#define PKCS11_TRUST_MODEL "p11-kit-trust"
/*
 * Every diagnostic line carries this prefix and a stable reason code so a
 * log can be correlated with the dialog a user saw. Only counts, the host of
 * the verified sign-in origin, and reason codes are logged: never PKCS #11
 * URIs, labels, serials, PINs, or callback URLs.
 */
#define SMARTCARD_AUTH_LOG "smartcard-auth: "

typedef struct {
	gchar *label;
	gchar *certificate_uri;
	gchar *private_key_uri;
} EitaasPkcs11Certificate;

typedef struct {
	guint tokens;
	guint trust_skipped;
	guint empty_tokens;
	gint last_empty_status;
	guint certificates;
	guint kept;
	guint dropped;
} EitaasDiscoveryStats;

typedef struct {
	WebKitAuthenticationRequest *request;
	GtkWidget *dialog;
	GPtrArray *certificates;
	EitaasDiscoveryStats stats;
	GCancellable *cancellable;
	gchar *error_message;
	guint timeout_source;
	gboolean abandoned;
	gboolean completed;
	gboolean timed_out;
} EitaasCertificateDiscovery;

typedef struct {
	gchar *certificate_uri;
	gchar *private_key_uri;
} EitaasCertificateLoadInput;

typedef struct {
	GtkWidget *dialog;
	GTlsCertificate *certificate;
	gchar *error_message;
	guint timeout_source;
	gboolean abandoned;
	gboolean completed;
	gboolean timed_out;
} EitaasCertificateLoad;

typedef struct {
	gchar *host;
	gchar *certificate_uri;
	gint64 expires_at;
	gboolean pin_submitted;
} EitaasCertificateAuthState;

typedef struct {
	GtkWindow *held;
	GtkWindow *window;
	gulong destroy_handler;
} EitaasAuthToplevel;

static gint discovery_active = 0;

static void certificate_auth_state_free(gpointer data)
{
	EitaasCertificateAuthState *state = data;
	if (!state)
		return;
	g_free(state->host);
	g_free(state->certificate_uri);
	g_free(state);
}

static void certificate_auth_state_clear(WebKitWebView *web_view)
{
	g_object_set_data(G_OBJECT(web_view), "rdp-certificate-transaction", NULL);
}

static void auth_toplevel_destroyed(GtkWidget *widget, gpointer user_data)
{
	(void)widget;
	EitaasAuthToplevel *toplevel = user_data;
	toplevel->window = NULL;
	toplevel->destroy_handler = 0;
}

/*
 * Keep the WebView toplevel alive across the nested main loops run by the
 * certificate dialogs. The strong reference guarantees the object outlives
 * every gtk_dialog_run(); the destroy handler clears the usable pointer so a
 * window closed during a nested loop is never reused as a transient parent.
 */
static void auth_toplevel_hold(EitaasAuthToplevel *toplevel, gpointer window)
{
	toplevel->held = g_object_ref(GTK_WINDOW(window));
	toplevel->window = toplevel->held;
	toplevel->destroy_handler = g_signal_connect(toplevel->held, "destroy",
	                                             G_CALLBACK(auth_toplevel_destroyed), toplevel);
}

static void auth_toplevel_release(EitaasAuthToplevel *toplevel)
{
	if (toplevel->destroy_handler)
		g_signal_handler_disconnect(toplevel->held, toplevel->destroy_handler);
	g_clear_object(&toplevel->held);
	toplevel->window = NULL;
}

/*
 * GError text from GLib's PKCS #11 loader may embed the object URI; cut the
 * message at the first URI so the log keeps the reason but not the label.
 */
static gchar *loggable_error(const gchar *message)
{
	if (!message)
		return g_strdup("unknown");
	const gchar *uri = strstr(message, "pkcs11:");
	return uri ? g_strndup(message, uri - message) : g_strdup(message);
}

static void log_rejection(const gchar *code, const gchar *reason)
{
	REMMINA_PLUGIN_WARNING(SMARTCARD_AUTH_LOG "%s (%s)", code, reason ? reason : "none");
}

static void show_error(EitaasAuthToplevel *toplevel, const gchar *code, const gchar *message)
{
	gchar *logged = loggable_error(message);

	REMMINA_PLUGIN_WARNING(SMARTCARD_AUTH_LOG "%s: %s", code, logged);
	g_free(logged);
	GtkWidget *dialog = gtk_message_dialog_new(toplevel->window, GTK_DIALOG_MODAL,
	                                           GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "%s", message);
	gtk_dialog_run(GTK_DIALOG(dialog));
	gtk_widget_destroy(dialog);
}

static void certificate_load_input_free(gpointer data)
{
	EitaasCertificateLoadInput *input = data;
	if (!input)
		return;
	g_free(input->certificate_uri);
	g_free(input->private_key_uri);
	g_free(input);
}

static void certificate_load_free(EitaasCertificateLoad *load)
{
	if (!load)
		return;
	if (load->timeout_source)
		g_source_remove(load->timeout_source);
	g_clear_object(&load->certificate);
	g_free(load->error_message);
	g_free(load);
}

static gboolean certificate_load_timeout(gpointer user_data)
{
	EitaasCertificateLoad *load = user_data;
	load->timeout_source = 0;
	load->timed_out = TRUE;
	REMMINA_PLUGIN_WARNING(SMARTCARD_AUTH_LOG "load-timeout (%d s)", PKCS11_TIMEOUT_SECONDS);
	if (load->dialog)
		gtk_dialog_response(GTK_DIALOG(load->dialog), GTK_RESPONSE_REJECT);
	return G_SOURCE_REMOVE;
}

static void certificate_load_thread(GTask *task, gpointer source, gpointer task_data,
	                                GCancellable *cancellable)
{
	(void)source;
	(void)cancellable;
	EitaasCertificateLoadInput *input = task_data;
	GError *error = NULL;
	GTlsCertificate *certificate = g_tls_certificate_new_from_pkcs11_uris(
		input->certificate_uri, input->private_key_uri, &error);
	if (certificate)
		g_task_return_pointer(task, certificate, g_object_unref);
	else if (error)
		g_task_return_error(task, error);
	else
		g_task_return_new_error(task, G_IO_ERROR, G_IO_ERROR_FAILED,
		                        "The selected smart-card certificate could not be loaded");
}

/*
 * Runs on the GTK thread once the loader thread finishes. When the dialog was
 * abandoned (cancelled or timed out) the load owns nothing but itself, so it
 * is released here without touching the dialog, the toplevel, or the request.
 */
static void certificate_load_done(GObject *source, GAsyncResult *result, gpointer user_data)
{
	(void)source;
	EitaasCertificateLoad *load = user_data;
	GError *error = NULL;
	load->certificate = g_task_propagate_pointer(G_TASK(result), &error);
	load->completed = TRUE;
	if (error) {
		gchar *logged = loggable_error(error->message);

		load->error_message = g_strdup(error->message);
		REMMINA_PLUGIN_WARNING(SMARTCARD_AUTH_LOG "load-error (%s/%d: %s)",
				       g_quark_to_string(error->domain), error->code, logged);
		g_free(logged);
	} else {
		REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "load-finished");
	}
	g_clear_error(&error);
	if (load->abandoned) {
		REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "load-result-discarded (dialog abandoned)");
		certificate_load_free(load);
		return;
	}
	gtk_dialog_response(GTK_DIALOG(load->dialog),
	                    load->certificate ? GTK_RESPONSE_ACCEPT : GTK_RESPONSE_REJECT);
}

/*
 * Load the selected certificate away from the GTK thread while a cancellable
 * progress dialog runs. Returns a new reference or NULL; every NULL return
 * has already shown its error (unless the user cancelled) and leaves exactly
 * one challenge cancellation to the caller.
 */
static GTlsCertificate *load_certificate_async(EitaasAuthToplevel *toplevel,
	                                           const EitaasPkcs11Certificate *choice)
{
	EitaasCertificateLoad *load = g_new0(EitaasCertificateLoad, 1);
	load->dialog = gtk_dialog_new_with_buttons(
		"Loading smart-card certificate", toplevel->window, GTK_DIALOG_MODAL,
		"Cancel", GTK_RESPONSE_CANCEL, NULL);
	GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
	GtkWidget *spinner = gtk_spinner_new();
	gtk_spinner_start(GTK_SPINNER(spinner));
	gtk_box_pack_start(GTK_BOX(box), spinner, FALSE, FALSE, 0);
	gtk_box_pack_start(GTK_BOX(box), gtk_label_new("Loading selected certificate…"),
	                   FALSE, FALSE, 0);
	gtk_container_set_border_width(GTK_CONTAINER(box), 12);
	gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(load->dialog))), box);
	gtk_widget_show_all(load->dialog);

	EitaasCertificateLoadInput *input = g_new0(EitaasCertificateLoadInput, 1);
	input->certificate_uri = g_strdup(choice->certificate_uri);
	input->private_key_uri = g_strdup(choice->private_key_uri);
	GTask *task = g_task_new(NULL, NULL, certificate_load_done, load);
	g_task_set_task_data(task, input, certificate_load_input_free);
	g_task_run_in_thread(task, certificate_load_thread);
	g_object_unref(task);
	load->timeout_source = g_timeout_add_seconds(PKCS11_TIMEOUT_SECONDS,
	                                             certificate_load_timeout, load);
	REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "load-start");

	gint response = gtk_dialog_run(GTK_DIALOG(load->dialog));
	gtk_widget_destroy(load->dialog);
	load->dialog = NULL;
	if (response != GTK_RESPONSE_ACCEPT || !load->certificate || !toplevel->window) {
		/*
		 * Mark the load abandoned before running another nested loop: the
		 * completion callback may fire inside show_error() and must then
		 * only free the load instead of responding to the destroyed dialog.
		 */
		gboolean abandoned = !load->completed;
		load->abandoned = abandoned;
		const gchar *message = load->timed_out
				       ? "Loading the smart-card certificate timed out" : load->error_message;
		if (message && toplevel->window)
			show_error(toplevel, load->timed_out ? "load-timeout" : "load-error", message);
		else if (!message)
			log_rejection("load-cancelled", toplevel->window ? "user" : "window-closed");
		if (!abandoned)
			certificate_load_free(load);
		return NULL;
	}
	GTlsCertificate *certificate = g_steal_pointer(&load->certificate);
	certificate_load_free(load);
	return certificate;
}

static void certificate_free(gpointer data)
{
	EitaasPkcs11Certificate *cert = data;
	if (!cert)
		return;
	g_free(cert->label);
	g_free(cert->certificate_uri);
	g_free(cert->private_key_uri);
	g_free(cert);
}

/*
 * Run the discovery tool and collect the "pkcs11:" lines it prints. The exit
 * status is reported through *exit_status (-1 when killed by a signal) so the
 * caller decides what a non-zero status means; only I/O failures,
 * cancellation, and output-limit violations set *error.
 */
static GPtrArray *command_urls(const gchar *const *argv, GCancellable *cancellable,
	                          gint *exit_status, GError **error)
{
	GPtrArray *urls = g_ptr_array_new_with_free_func(g_free);
	GSubprocess *process = g_subprocess_newv(argv,
	    G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE, error);

	*exit_status = -1;
	if (!process)
		return urls;
	GInputStream *stream = g_subprocess_get_stdout_pipe(process);
	GByteArray *output = g_byte_array_sized_new(4096);
	guint8 buffer[4096];
	while (output->len <= PKCS11_MAX_OUTPUT) {
		gssize count = g_input_stream_read(stream, buffer, sizeof(buffer), cancellable, error);
		if (count <= 0)
			break;
		if ((gsize)count > PKCS11_MAX_OUTPUT - output->len) {
			g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
			                    "PKCS11 discovery output exceeded its limit");
			break;
		}
		g_byte_array_append(output, buffer, (guint)count);
	}
	if (*error)
		g_subprocess_force_exit(process);
	else if (!g_subprocess_wait(process, cancellable, error))
		g_subprocess_force_exit(process);
	else if (g_subprocess_get_if_exited(process))
		*exit_status = g_subprocess_get_exit_status(process);
	if (!*error) {
		g_byte_array_append(output, (const guint8 *)"", 1);
		gchar **lines = g_strsplit((const gchar *)output->data, "\n", -1);
		for (gchar **line = lines; line && *line; line++) {
			if (strlen(*line) > PKCS11_MAX_URI) {
				g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
				                    "PKCS11 URI exceeded its limit");
				break;
			}
			if (g_str_has_prefix(*line, "pkcs11:"))
				g_ptr_array_add(urls, g_strdup(*line));
		}
		g_strfreev(lines);
	}
	g_byte_array_unref(output);
	g_object_unref(process);
	return urls;
}

static gchar *uri_attribute(const gchar *uri, const gchar *name)
{
	gchar **fields = g_strsplit(uri + (g_str_has_prefix(uri, "pkcs11:") ? 7 : 0), ";", -1);
	gchar *prefix = g_strdup_printf("%s=", name);
	gchar *result = NULL;
	for (gchar **field = fields; field && *field; field++) {
		if (g_str_has_prefix(*field, prefix)) {
			result = g_strdup(*field + strlen(prefix));
			break;
		}
	}
	g_free(prefix);
	g_strfreev(fields);
	return result;
}

static gboolean authentication_label(const gchar *label)
{
	gchar *lower = g_utf8_strdown(label, -1);
	gboolean match = strstr(lower, "piv") || strstr(lower, "auth") || strstr(lower, "identity");
	g_free(lower);
	return match;
}

static gchar *private_key_selector(const gchar *certificate_uri)
{
	const gchar *query = strchr(certificate_uri, '?');
	gchar *attributes = query ? g_strndup(certificate_uri + 7, query - certificate_uri - 7)
	                          : g_strdup(certificate_uri + 7);
	gchar **parts = g_strsplit(attributes, ";", -1);
	GString *result = g_string_new("pkcs11:");
	for (gchar **part = parts; part && *part; part++) {
		if (g_str_has_prefix(*part, "object=") || g_str_has_prefix(*part, "type="))
			continue;
		if (result->len > 7)
			g_string_append_c(result, ';');
		g_string_append(result, *part);
	}
	if (result->len > 7)
		g_string_append_c(result, ';');
	g_string_append(result, "type=private");
	if (query)
		g_string_append(result, query);
	g_strfreev(parts);
	g_free(attributes);
	return g_string_free(result, FALSE);
}

/*
 * Runs on the discovery worker thread; only counts are collected here so the
 * GTK thread can log them once discovery completes.
 */
static GPtrArray *enumerate_certificates(GCancellable *cancellable, EitaasDiscoveryStats *stats,
	                         GError **error)
{
	GPtrArray *result = g_ptr_array_new_with_free_func(certificate_free);
	if (!g_file_test(PKCS11_TOOL, G_FILE_TEST_IS_EXECUTABLE)) {
		g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND,
		                    "The configured PKCS11 discovery tool is unavailable");
		return result;
	}
	const gchar *token_args[] = { PKCS11_TOOL, "--list-token-urls", NULL };
	gint status = -1;
	GPtrArray *tokens = command_urls(token_args, cancellable, &status, error);

	stats->tokens = tokens->len;
	if (!*error && status != 0)
		g_set_error(error, G_IO_ERROR, G_IO_ERROR_FAILED,
		            "PKCS11 token discovery failed (exit status %d)", status);
	if (!*error && tokens->len > PKCS11_MAX_TOKENS)
		g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
		                    "PKCS11 token count exceeded its limit");
	for (guint i = 0; !*error && i < tokens->len && i < PKCS11_MAX_TOKENS; i++) {
		const gchar *token = g_ptr_array_index(tokens, i);
		gchar *model = uri_attribute(token, "model");
		gboolean trust = g_strcmp0(model, PKCS11_TRUST_MODEL) == 0;

		g_free(model);
		if (trust) {
			stats->trust_skipped++;
			continue;
		}
		const gchar *cert_args[] = { PKCS11_TOOL, "--list-certs", "--only-urls", token, NULL };
		GPtrArray *certs = command_urls(cert_args, cancellable, &status, error);

		/*
		 * p11tool exits non-zero for a token without matching objects
		 * ("No matching objects found"); with no URL printed that is an
		 * empty token, not a discovery failure. A non-zero status
		 * alongside URLs is malformed output and stays fatal, as is a
		 * tool killed by a signal (status < 0).
		 */
		if (!*error && status < 0)
			g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_FAILED,
			                    "PKCS11 discovery tool terminated by signal");
		if (!*error && status != 0) {
			if (certs->len == 0) {
				stats->empty_tokens++;
				stats->last_empty_status = status;
				g_ptr_array_unref(certs);
				continue;
			}
			g_set_error(error, G_IO_ERROR, G_IO_ERROR_FAILED,
			            "PKCS11 certificate listing failed (exit status %d)", status);
		}
		stats->certificates += certs->len;
		if (!*error && certs->len > PKCS11_MAX_CERTIFICATES - result->len)
			g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
			                    "PKCS11 certificate count exceeded its limit");
		for (guint j = 0; !*error && j < certs->len &&
		                  result->len < PKCS11_MAX_CERTIFICATES; j++) {
			const gchar *uri = g_ptr_array_index(certs, j);
			gchar *id = uri_attribute(uri, "id");
			if (!id || !*id) {
				g_free(id);
				continue;
			}
			g_free(id);
			gchar *encoded = uri_attribute(uri, "object");
			gchar *label = encoded && strlen(encoded) <= PKCS11_MAX_LABEL * 3
			                 ? g_uri_unescape_string(encoded, NULL) : NULL;
			g_free(encoded);
			if (!label)
				label = g_strdup("Smart-card authentication certificate");
			if (!authentication_label(label)) {
				stats->dropped++;
				g_free(label);
				continue;
			}
			stats->kept++;
			EitaasPkcs11Certificate *cert = g_new0(EitaasPkcs11Certificate, 1);
			cert->label = label;
			cert->certificate_uri = g_strdup(uri);
			cert->private_key_uri = private_key_selector(uri);
			g_ptr_array_add(result, cert);
		}
		g_ptr_array_unref(certs);
	}
	g_ptr_array_unref(tokens);
	return result;
}

static void discovery_free(EitaasCertificateDiscovery *discovery)
{
	if (!discovery)
		return;
	g_clear_object(&discovery->request);
	if (discovery->certificates)
		g_ptr_array_unref(discovery->certificates);
	if (discovery->timeout_source)
		g_source_remove(discovery->timeout_source);
	g_clear_object(&discovery->cancellable);
	g_free(discovery->error_message);
	g_atomic_int_set(&discovery_active, 0);
	g_free(discovery);
}

static gboolean discovery_timeout(gpointer user_data)
{
	EitaasCertificateDiscovery *discovery = user_data;
	discovery->timeout_source = 0;
	discovery->timed_out = TRUE;
	REMMINA_PLUGIN_WARNING(SMARTCARD_AUTH_LOG "discovery-timeout (%d s)", PKCS11_TIMEOUT_SECONDS);
	g_cancellable_cancel(discovery->cancellable);
	return G_SOURCE_REMOVE;
}

static void quit_oneshot_application(void)
{
	if (g_strcmp0(g_getenv("EITAAS_REMMINA_ONESHOT"), "1") != 0)
		return;
	GApplication *application = g_application_get_default();
	REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "oneshot-quit (application=%d)", application != NULL);
	if (application)
		g_application_quit(application);
}

static void enumerate_certificates_thread(GTask *task, gpointer source_object,
	                                      gpointer task_data, GCancellable *cancellable)
{
	(void)source_object;
	EitaasDiscoveryStats *stats = task_data;
	GError *error = NULL;
	GPtrArray *certificates = enumerate_certificates(cancellable, stats, &error);
	if (error) {
		g_ptr_array_unref(certificates);
		g_task_return_error(task, error);
	} else {
		g_task_return_pointer(task, certificates, (GDestroyNotify)g_ptr_array_unref);
	}
}

static void enumerate_certificates_done(GObject *source_object, GAsyncResult *result,
	                                    gpointer user_data)
{
	(void)source_object;
	EitaasCertificateDiscovery *discovery = user_data;
	GError *error = NULL;
	discovery->certificates = g_task_propagate_pointer(G_TASK(result), &error);
	discovery->completed = TRUE;
	if (discovery->stats.trust_skipped)
		REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "discovery-token-skipped-trust (count=%u)",
				     discovery->stats.trust_skipped);
	if (discovery->stats.empty_tokens)
		REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "discovery-token-empty (count=%u last-exit=%d)",
				     discovery->stats.empty_tokens, discovery->stats.last_empty_status);
	REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "discovery-finished (tokens=%u certificates=%u "
			     "label-filter kept=%u dropped=%u)", discovery->stats.tokens,
			     discovery->stats.certificates, discovery->stats.kept, discovery->stats.dropped);
	if (error)
		discovery->error_message = g_strdup(discovery->timed_out
		    ? "Smart-card certificate discovery timed out" : error->message);
	if (discovery->abandoned) {
		log_rejection("discovery-result-discarded", error ? "error" : "dialog abandoned");
		g_clear_error(&error);
		discovery_free(discovery);
		return;
	}
	gtk_dialog_response(GTK_DIALOG(discovery->dialog),
	                    error ? GTK_RESPONSE_REJECT : GTK_RESPONSE_ACCEPT);
	g_clear_error(&error);
}

static GPtrArray *discover_certificates(EitaasAuthToplevel *toplevel,
	                                   WebKitAuthenticationRequest *request)
{
	if (!g_atomic_int_compare_and_exchange(&discovery_active, 0, 1)) {
		log_rejection("discovery-busy", "another discovery is running");
		webkit_authentication_request_cancel(request);
		return NULL;
	}
	EitaasCertificateDiscovery *discovery = g_new0(EitaasCertificateDiscovery, 1);
	discovery->request = g_object_ref(request);
	discovery->cancellable = g_cancellable_new();
	discovery->dialog = gtk_dialog_new_with_buttons(
		"Reading smart card", toplevel->window, GTK_DIALOG_MODAL,
		"Cancel", GTK_RESPONSE_CANCEL, NULL);
	GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
	GtkWidget *spinner = gtk_spinner_new();
	GtkWidget *label = gtk_label_new("Discovering authentication certificates…");
	gtk_spinner_start(GTK_SPINNER(spinner));
	gtk_box_pack_start(GTK_BOX(box), spinner, FALSE, FALSE, 0);
	gtk_box_pack_start(GTK_BOX(box), label, FALSE, FALSE, 0);
	gtk_container_set_border_width(GTK_CONTAINER(box), 12);
	gtk_container_add(GTK_CONTAINER(
		gtk_dialog_get_content_area(GTK_DIALOG(discovery->dialog))), box);
	gtk_widget_show_all(discovery->dialog);

	GTask *task = g_task_new(NULL, discovery->cancellable, enumerate_certificates_done, discovery);
	g_task_set_task_data(task, &discovery->stats, NULL);
	g_task_run_in_thread(task, enumerate_certificates_thread);
	g_object_unref(task);
	discovery->timeout_source = g_timeout_add_seconds(PKCS11_TIMEOUT_SECONDS,
	                                                 discovery_timeout, discovery);
	REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "discovery-start (tool=" PKCS11_TOOL ")");

	gint response = gtk_dialog_run(GTK_DIALOG(discovery->dialog));
	gtk_widget_destroy(discovery->dialog);
	discovery->dialog = NULL;
	if (response != GTK_RESPONSE_ACCEPT || !toplevel->window) {
		if (discovery->completed && discovery->error_message && toplevel->window)
			show_error(toplevel, discovery->timed_out ? "discovery-timeout" : "discovery-error",
				   discovery->error_message);
		else
			log_rejection("discovery-cancelled", !toplevel->window ? "window-closed"
				      : discovery->completed ? "error-after-close" : "user");
		if (discovery->completed)
			discovery_free(discovery);
		else {
			discovery->abandoned = TRUE;
			g_cancellable_cancel(discovery->cancellable);
		}
		webkit_authentication_request_cancel(request);
		if (toplevel->window)
			gtk_window_close(toplevel->window);
		quit_oneshot_application();
		return NULL;
	}

	GPtrArray *certificates = discovery->certificates;
	discovery->certificates = NULL;
	discovery_free(discovery);
	return certificates;
}

/*
 * Entra ID issues the client-certificate challenge either from the verified
 * authority itself or from its dedicated CERTAUTH_HOST_PREFIX subdomain. Only
 * those two exact names are trusted; no suffix or substring matching. Hosts
 * with a trailing dot or in a different (IDNA/Unicode) form are not
 * normalised and therefore fail closed.
 */
static gboolean host_is_authority_or_certauth(const gchar *host, const gchar *authority)
{
	if (g_ascii_strcasecmp(host, authority) == 0)
		return TRUE;
	gchar *certauth = g_strconcat(CERTAUTH_HOST_PREFIX, authority, NULL);
	gboolean match = g_ascii_strcasecmp(host, certauth) == 0;
	g_free(certauth);
	return match;
}

/*
 * Returns the verified challenge host or NULL; *reason names the first check
 * that failed so the rejection can be logged without repeating the checks.
 */
static const gchar *trusted_request_host(WebKitWebView *web_view,
	                    WebKitAuthenticationRequest *request,
	                    const gchar **reason)
{
	*reason = NULL;
	if (webkit_authentication_request_is_for_proxy(request)) {
		*reason = "proxy-challenge";
		return NULL;
	}
	const gchar *authority = g_object_get_data(G_OBJECT(web_view), "rdp-authentication-host");
	const gchar *host = webkit_authentication_request_get_host(request);
	WebKitSecurityOrigin *origin = webkit_authentication_request_get_security_origin(request);
	const gchar *protocol = origin ? webkit_security_origin_get_protocol(origin) : NULL;
	const gchar *origin_host = origin ? webkit_security_origin_get_host(origin) : NULL;
	guint port = origin ? webkit_security_origin_get_port(origin) : 0;

	if (!authority)
		*reason = "no-authentication-host";
	else if (!host || !origin_host || !protocol)
		*reason = "no-security-origin";
	else if (g_ascii_strcasecmp(protocol, "https") != 0)
		*reason = "origin-not-https";
	else if (g_ascii_strcasecmp(origin_host, host) != 0)
		*reason = "origin-host-mismatch";
	else if (!host_is_authority_or_certauth(host, authority))
		*reason = "host-not-authority";
	else if (port != 0 && port != 443)
		*reason = "origin-port";
	if (origin)
		webkit_security_origin_unref(origin);
	return *reason ? NULL : host;
}

static const gchar *scheme_name(WebKitAuthenticationScheme scheme)
{
	return scheme == WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_REQUESTED
	       ? "client-certificate" : "client-certificate-pin";
}

gboolean eitaas_webview_authenticate(WebKitWebView *web_view,
	WebKitAuthenticationRequest *request, gpointer parent_data)
{
	WebKitAuthenticationScheme scheme = webkit_authentication_request_get_scheme(request);
	if (scheme != WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_REQUESTED &&
		scheme != WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_PIN_REQUESTED)
		return FALSE;
	const gchar *challenge_host = webkit_authentication_request_get_host(request);
	GApplication *application = g_application_get_default();
	const gchar *application_id = application ? g_application_get_application_id(application) : NULL;
	REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "challenge-received (scheme=%s unverified-host=%s port=%u proxy=%d "
			     "retry=%d application=%s remote=%d)", scheme_name(scheme),
			     challenge_host ? challenge_host : "",
			     webkit_authentication_request_get_port(request),
			     webkit_authentication_request_is_for_proxy(request),
			     webkit_authentication_request_is_retry(request),
			     application_id ? application_id : "",
			     application ? g_application_get_is_remote(application) : 0);
	EitaasAuthToplevel toplevel = { 0 };
	auth_toplevel_hold(&toplevel, parent_data);
	const gchar *reason = NULL;
	if (scheme == WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_REQUESTED) {
		certificate_auth_state_clear(web_view);
		const gchar *request_host = trusted_request_host(web_view, request, &reason);
		if (!request_host) {
			log_rejection("origin-rejected", reason);
			webkit_authentication_request_cancel(request);
			auth_toplevel_release(&toplevel);
			return TRUE;
		}
		REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "challenge-accepted (host=%s)", request_host);
		GPtrArray *certs = discover_certificates(&toplevel, request);
		if (!certs) {
			auth_toplevel_release(&toplevel);
			return TRUE;
		}
		if (certs->len == 0) {
			gchar *message = g_strdup_printf(
				"No usable smart-card authentication certificates were found for %s",
				request_host);
			show_error(&toplevel, "discovery-empty", message);
			g_free(message);
			g_ptr_array_unref(certs);
			webkit_authentication_request_cancel(request);
			auth_toplevel_release(&toplevel);
			return TRUE;
		}
		gchar *dialog_title = g_strdup_printf(
			"Select smart-card authentication certificate for %s", request_host);
		GtkWidget *dialog = gtk_dialog_new_with_buttons(
			dialog_title, toplevel.window, GTK_DIALOG_MODAL,
			"Cancel", GTK_RESPONSE_CANCEL, "Continue", GTK_RESPONSE_ACCEPT, NULL);
		g_free(dialog_title);
		GtkWidget *combo = gtk_combo_box_text_new();
		for (guint i = 0; i < certs->len; i++)
			gtk_combo_box_text_append_text(GTK_COMBO_BOX_TEXT(combo),
				((EitaasPkcs11Certificate *)g_ptr_array_index(certs, i))->label);
		gtk_combo_box_set_active(GTK_COMBO_BOX(combo), 0);
		gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(dialog))), combo);
		gtk_widget_show_all(dialog);
		gint response = gtk_dialog_run(GTK_DIALOG(dialog));
		gint selected = gtk_combo_box_get_active(GTK_COMBO_BOX(combo));
		if (!toplevel.window)
			response = GTK_RESPONSE_CANCEL;
		if (response == GTK_RESPONSE_ACCEPT && selected >= 0 && (guint)selected < certs->len) {
			EitaasPkcs11Certificate *choice = g_ptr_array_index(certs, selected);

			REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "certificate-selected (index=%d of %u)",
					     selected, certs->len);
			GTlsCertificate *cert = load_certificate_async(&toplevel, choice);
			if (cert) {
				REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "certificate-submitted (host=%s)",
						     request_host);
				EitaasCertificateAuthState *state = g_new0(EitaasCertificateAuthState, 1);
				state->host = g_strdup(request_host);
				state->certificate_uri = g_strdup(choice->certificate_uri);
				state->expires_at = g_get_monotonic_time() + (2 * G_TIME_SPAN_MINUTE);
				g_object_set_data_full(G_OBJECT(web_view), "rdp-certificate-transaction",
				                       state, certificate_auth_state_free);
				WebKitCredential *credential = webkit_credential_new_for_certificate(
					cert, WEBKIT_CREDENTIAL_PERSISTENCE_NONE);
				webkit_authentication_request_authenticate(request, credential);
				webkit_credential_free(credential);
				g_object_unref(cert);
			} else {
				webkit_authentication_request_cancel(request);
			}
		} else {
			log_rejection("selection-cancelled", !toplevel.window ? "window-closed" : "user");
			webkit_authentication_request_cancel(request);
		}
		gtk_widget_destroy(dialog);
		g_ptr_array_unref(certs);
		auth_toplevel_release(&toplevel);
		return TRUE;
	}
	const gchar *request_host = trusted_request_host(web_view, request, &reason);
	EitaasCertificateAuthState *state = g_object_get_data(
		G_OBJECT(web_view), "rdp-certificate-transaction");
	gboolean retrying = webkit_authentication_request_is_retry(request);

	if (!request_host)
		reason = reason ? reason : "origin-rejected";
	else if (!state || !state->certificate_uri)
		reason = "no-certificate-transaction";
	else if (g_get_monotonic_time() >= state->expires_at)
		reason = "transaction-expired";
	else if (g_ascii_strcasecmp(request_host, state->host) != 0)
		reason = "transaction-host-mismatch";
	else if (state->pin_submitted && !retrying)
		reason = "pin-already-submitted";
	if (reason) {
		log_rejection("pin-rejected", reason);
		certificate_auth_state_clear(web_view);
		webkit_authentication_request_cancel(request);
		auth_toplevel_release(&toplevel);
		return TRUE;
	}
	gchar *dialog_title = g_strdup_printf("Smart-card PIN for %s", request_host);
	GtkWidget *dialog = gtk_dialog_new_with_buttons(
		dialog_title, toplevel.window, GTK_DIALOG_MODAL, "Cancel", GTK_RESPONSE_CANCEL,
		"Continue", GTK_RESPONSE_ACCEPT, NULL);
	g_free(dialog_title);
	GtkWidget *entry = gtk_entry_new();
	gtk_entry_set_visibility(GTK_ENTRY(entry), FALSE);
	gtk_entry_set_input_purpose(GTK_ENTRY(entry), GTK_INPUT_PURPOSE_PIN);
	gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(dialog))), entry);
	gtk_widget_show_all(dialog);
	REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "pin-requested (host=%s retry=%d)", request_host, retrying);
	gint response = gtk_dialog_run(GTK_DIALOG(dialog));
	state = g_object_get_data(G_OBJECT(web_view), "rdp-certificate-transaction");
	if (response == GTK_RESPONSE_ACCEPT && toplevel.window && state) {
		REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG "pin-submitted (host=%s)", request_host);
		WebKitCredential *credential = webkit_credential_new_for_certificate_pin(
			gtk_entry_get_text(GTK_ENTRY(entry)), WEBKIT_CREDENTIAL_PERSISTENCE_NONE);
		webkit_authentication_request_authenticate(request, credential);
		webkit_credential_free(credential);
		state->pin_submitted = TRUE;
	} else {
		log_rejection("pin-cancelled", !toplevel.window ? "window-closed"
			      : !state ? "transaction-cleared" : "user");
		webkit_authentication_request_cancel(request);
		certificate_auth_state_clear(web_view);
	}
	gtk_entry_set_text(GTK_ENTRY(entry), "");
	gtk_widget_destroy(dialog);
	auth_toplevel_release(&toplevel);
	return TRUE;
}
