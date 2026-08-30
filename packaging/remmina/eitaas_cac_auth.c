// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 Stephen Trotter

#include "eitaas_cac_auth.h"

#include <gtk/gtk.h>
#include <string.h>

#define PKCS11_TOOL "/usr/bin/p11tool"
#define PKCS11_TIMEOUT_SECONDS 15
#define PKCS11_MAX_OUTPUT (256 * 1024)
#define PKCS11_MAX_URI 4096
#define PKCS11_MAX_LABEL 256
#define PKCS11_MAX_TOKENS 16
#define PKCS11_MAX_CERTIFICATES 64

typedef struct {
	gchar *label;
	gchar *certificate_uri;
	gchar *private_key_uri;
} EitaasPkcs11Certificate;

typedef struct {
	WebKitAuthenticationRequest *request;
	GtkWidget *dialog;
	GPtrArray *certificates;
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
	g_signal_handler_disconnect(toplevel->held, toplevel->destroy_handler);
	g_clear_object(&toplevel->held);
	toplevel->window = NULL;
}

static void show_error(EitaasAuthToplevel *toplevel, const gchar *message)
{
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
	if (error)
		load->error_message = g_strdup(error->message);
	g_clear_error(&error);
	if (load->abandoned) {
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

	gint response = gtk_dialog_run(GTK_DIALOG(load->dialog));
	gtk_widget_destroy(load->dialog);
	load->dialog = NULL;
	if (response != GTK_RESPONSE_ACCEPT || !load->certificate || !toplevel->window) {
		const gchar *message = load->timed_out
		                       ? "Loading the smart-card certificate timed out" : load->error_message;
		if (message && toplevel->window)
			show_error(toplevel, message);
		if (load->completed)
			certificate_load_free(load);
		else
			load->abandoned = TRUE;
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

static GPtrArray *command_urls(const gchar *const *argv, GCancellable *cancellable,
	                          GError **error)
{
	GPtrArray *urls = g_ptr_array_new_with_free_func(g_free);
	GSubprocess *process = g_subprocess_newv(argv,
	    G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE, error);
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
	if (error && *error)
		g_subprocess_force_exit(process);
	if ((!error || !*error) && !g_subprocess_wait_check(process, cancellable, error))
		g_subprocess_force_exit(process);
	if (!error || !*error) {
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

static GPtrArray *enumerate_certificates(GCancellable *cancellable, GError **error)
{
	GPtrArray *result = g_ptr_array_new_with_free_func(certificate_free);
	if (!g_file_test(PKCS11_TOOL, G_FILE_TEST_IS_EXECUTABLE)) {
		g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND,
		                    "The configured PKCS11 discovery tool is unavailable");
		return result;
	}
	const gchar *token_args[] = { PKCS11_TOOL, "--list-token-urls", NULL };
	GPtrArray *tokens = command_urls(token_args, cancellable, error);
	if ((!error || !*error) && tokens->len > PKCS11_MAX_TOKENS)
		g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
		                    "PKCS11 token count exceeded its limit");
	for (guint i = 0; (!error || !*error) && i < tokens->len && i < PKCS11_MAX_TOKENS; i++) {
		const gchar *cert_args[] = { PKCS11_TOOL, "--list-certs", "--only-urls",
		                       g_ptr_array_index(tokens, i), NULL };
		GPtrArray *certs = command_urls(cert_args, cancellable, error);
		if ((!error || !*error) && certs->len > PKCS11_MAX_CERTIFICATES - result->len)
			g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
			                    "PKCS11 certificate count exceeded its limit");
		for (guint j = 0; (!error || !*error) && j < certs->len &&
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
				g_free(label);
				continue;
			}
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
	g_cancellable_cancel(discovery->cancellable);
	return G_SOURCE_REMOVE;
}

static void quit_oneshot_application(void)
{
	if (g_strcmp0(g_getenv("EITAAS_REMMINA_ONESHOT"), "1") != 0)
		return;
	GApplication *application = g_application_get_default();
	if (application)
		g_application_quit(application);
}

static void enumerate_certificates_thread(GTask *task, gpointer source_object,
	                                      gpointer task_data, GCancellable *cancellable)
{
	(void)source_object;
	(void)task_data;
	GError *error = NULL;
	GPtrArray *certificates = enumerate_certificates(cancellable, &error);
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
	if (error)
		discovery->error_message = g_strdup(discovery->timed_out
		    ? "Smart-card certificate discovery timed out" : error->message);
	if (discovery->abandoned) {
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
	g_task_run_in_thread(task, enumerate_certificates_thread);
	g_object_unref(task);
	discovery->timeout_source = g_timeout_add_seconds(PKCS11_TIMEOUT_SECONDS,
	                                                 discovery_timeout, discovery);

	gint response = gtk_dialog_run(GTK_DIALOG(discovery->dialog));
	gtk_widget_destroy(discovery->dialog);
	discovery->dialog = NULL;
	if (response != GTK_RESPONSE_ACCEPT || !toplevel->window) {
		if (discovery->completed && discovery->error_message && toplevel->window)
			show_error(toplevel, discovery->error_message);
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

static const gchar *trusted_request_host(WebKitWebView *web_view,
	                                    WebKitAuthenticationRequest *request)
{
	if (webkit_authentication_request_is_for_proxy(request))
		return NULL;
	const gchar *expected = g_object_get_data(G_OBJECT(web_view), "rdp-authentication-host");
	const gchar *host = webkit_authentication_request_get_host(request);
	WebKitSecurityOrigin *origin = webkit_authentication_request_get_security_origin(request);
	const gchar *protocol = origin ? webkit_security_origin_get_protocol(origin) : NULL;
	const gchar *origin_host = origin ? webkit_security_origin_get_host(origin) : NULL;
	guint port = origin ? webkit_security_origin_get_port(origin) : 0;
	gboolean valid = expected && host && origin_host && protocol &&
	                 g_ascii_strcasecmp(protocol, "https") == 0 &&
	                 g_ascii_strcasecmp(host, expected) == 0 &&
	                 g_ascii_strcasecmp(origin_host, expected) == 0 &&
	                 (port == 0 || port == 443);
	if (origin)
		webkit_security_origin_unref(origin);
	return valid ? expected : NULL;
}

gboolean eitaas_webview_authenticate(WebKitWebView *web_view,
	WebKitAuthenticationRequest *request, gpointer parent_data)
{
	WebKitAuthenticationScheme scheme = webkit_authentication_request_get_scheme(request);
	if (scheme != WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_REQUESTED &&
	    scheme != WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_PIN_REQUESTED)
		return FALSE;
	EitaasAuthToplevel toplevel = { 0 };
	auth_toplevel_hold(&toplevel, parent_data);
	if (scheme == WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_REQUESTED) {
		certificate_auth_state_clear(web_view);
		const gchar *request_host = trusted_request_host(web_view, request);
		if (!request_host) {
			webkit_authentication_request_cancel(request);
			auth_toplevel_release(&toplevel);
			return TRUE;
		}
		GPtrArray *certs = discover_certificates(&toplevel, request);
		if (!certs) {
			auth_toplevel_release(&toplevel);
			return TRUE;
		}
		if (certs->len == 0) {
			gchar *message = g_strdup_printf(
				"No usable smart-card authentication certificates were found for %s",
				request_host);
			show_error(&toplevel, message);
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
			GTlsCertificate *cert = load_certificate_async(&toplevel, choice);
			if (cert) {
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
			webkit_authentication_request_cancel(request);
		}
		gtk_widget_destroy(dialog);
		g_ptr_array_unref(certs);
		auth_toplevel_release(&toplevel);
		return TRUE;
	}
	const gchar *request_host = trusted_request_host(web_view, request);
	EitaasCertificateAuthState *state = g_object_get_data(
		G_OBJECT(web_view), "rdp-certificate-transaction");
	gboolean retrying = webkit_authentication_request_is_retry(request);
	if (!request_host || !state || !state->certificate_uri ||
	    g_get_monotonic_time() >= state->expires_at ||
	    g_ascii_strcasecmp(request_host, state->host) != 0 ||
	    (state->pin_submitted && !retrying)) {
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
	gint response = gtk_dialog_run(GTK_DIALOG(dialog));
	state = g_object_get_data(G_OBJECT(web_view), "rdp-certificate-transaction");
	if (response == GTK_RESPONSE_ACCEPT && toplevel.window && state) {
		WebKitCredential *credential = webkit_credential_new_for_certificate_pin(
			gtk_entry_get_text(GTK_ENTRY(entry)), WEBKIT_CREDENTIAL_PERSISTENCE_NONE);
		webkit_authentication_request_authenticate(request, credential);
		webkit_credential_free(credential);
		state->pin_submitted = TRUE;
	} else {
		webkit_authentication_request_cancel(request);
		certificate_auth_state_clear(web_view);
	}
	gtk_entry_set_text(GTK_ENTRY(entry), "");
	gtk_widget_destroy(dialog);
	auth_toplevel_release(&toplevel);
	return TRUE;
}
