#include "eitaas_cac_auth.h"

#include <gtk/gtk.h>
#include <string.h>

typedef struct {
	gchar *label;
	gchar *certificate_uri;
	gchar *private_key_uri;
} EitaasPkcs11Certificate;

typedef struct {
	WebKitAuthenticationRequest *request;
	GtkWidget *dialog;
	GPtrArray *certificates;
	gboolean abandoned;
} EitaasCertificateDiscovery;

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

static GPtrArray *command_urls(gchar **argv)
{
	gchar *output = NULL;
	gint status = 0;
	GError *error = NULL;
	GPtrArray *urls = g_ptr_array_new_with_free_func(g_free);
	if (g_spawn_sync(NULL, argv, NULL, G_SPAWN_STDERR_TO_DEV_NULL, NULL, NULL,
	                 &output, NULL, &status, &error) && status == 0 && output) {
		gchar **lines = g_strsplit(output, "\n", -1);
		for (gchar **line = lines; line && *line; line++)
			if (g_str_has_prefix(*line, "pkcs11:"))
				g_ptr_array_add(urls, g_strdup(*line));
		g_strfreev(lines);
	}
	g_clear_error(&error);
	g_free(output);
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

static GPtrArray *enumerate_certificates(void)
{
	GPtrArray *result = g_ptr_array_new_with_free_func(certificate_free);
	gchar *token_args[] = { "/usr/bin/p11tool", "--list-token-urls", NULL };
	GPtrArray *tokens = command_urls(token_args);
	for (guint i = 0; i < tokens->len; i++) {
		gchar *cert_args[] = { "/usr/bin/p11tool", "--list-certs", "--only-urls",
		                       g_ptr_array_index(tokens, i), NULL };
		GPtrArray *certs = command_urls(cert_args);
		for (guint j = 0; j < certs->len; j++) {
			const gchar *uri = g_ptr_array_index(certs, j);
			gchar *id = uri_attribute(uri, "id");
			if (!id || !*id) {
				g_free(id);
				continue;
			}
			g_free(id);
			gchar *encoded = uri_attribute(uri, "object");
			gchar *label = encoded ? g_uri_unescape_string(encoded, NULL) : NULL;
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
	g_free(discovery);
}

static void enumerate_certificates_thread(GTask *task, gpointer source_object,
	                                      gpointer task_data, GCancellable *cancellable)
{
	(void)source_object;
	(void)task_data;
	(void)cancellable;
	g_task_return_pointer(task, enumerate_certificates(), (GDestroyNotify)g_ptr_array_unref);
}

static void enumerate_certificates_done(GObject *source_object, GAsyncResult *result,
	                                    gpointer user_data)
{
	(void)source_object;
	EitaasCertificateDiscovery *discovery = user_data;
	discovery->certificates = g_task_propagate_pointer(G_TASK(result), NULL);
	if (discovery->abandoned) {
		discovery_free(discovery);
		return;
	}
	gtk_dialog_response(GTK_DIALOG(discovery->dialog), GTK_RESPONSE_ACCEPT);
}

static GPtrArray *discover_certificates(GtkWindow *parent,
	                                   WebKitAuthenticationRequest *request)
{
	EitaasCertificateDiscovery *discovery = g_new0(EitaasCertificateDiscovery, 1);
	discovery->request = g_object_ref(request);
	discovery->dialog = gtk_dialog_new_with_buttons(
		"Reading smart card", parent, GTK_DIALOG_MODAL,
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

	GTask *task = g_task_new(NULL, NULL, enumerate_certificates_done, discovery);
	g_task_run_in_thread(task, enumerate_certificates_thread);
	g_object_unref(task);

	gint response = gtk_dialog_run(GTK_DIALOG(discovery->dialog));
	gtk_widget_destroy(discovery->dialog);
	discovery->dialog = NULL;
	if (response != GTK_RESPONSE_ACCEPT) {
		discovery->abandoned = TRUE;
		webkit_authentication_request_cancel(request);
		gtk_window_close(parent);
		return NULL;
	}

	GPtrArray *certificates = discovery->certificates;
	discovery->certificates = NULL;
	discovery_free(discovery);
	return certificates;
}

gboolean eitaas_webview_authenticate(WebKitWebView *web_view,
	WebKitAuthenticationRequest *request, gpointer parent_data)
{
	(void)web_view;
	WebKitAuthenticationScheme scheme = webkit_authentication_request_get_scheme(request);
	GtkWindow *parent = GTK_WINDOW(parent_data);
	if (scheme == WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_REQUESTED) {
		GPtrArray *certs = discover_certificates(parent, request);
		if (!certs)
			return TRUE;
		if (certs->len == 0) {
			g_ptr_array_unref(certs);
			webkit_authentication_request_cancel(request);
			return TRUE;
		}
		GtkWidget *dialog = gtk_dialog_new_with_buttons(
			"Select smart-card authentication certificate", parent, GTK_DIALOG_MODAL,
			"Cancel", GTK_RESPONSE_CANCEL, "Continue", GTK_RESPONSE_ACCEPT, NULL);
		GtkWidget *combo = gtk_combo_box_text_new();
		for (guint i = 0; i < certs->len; i++)
			gtk_combo_box_text_append_text(GTK_COMBO_BOX_TEXT(combo),
				((EitaasPkcs11Certificate *)g_ptr_array_index(certs, i))->label);
		gtk_combo_box_set_active(GTK_COMBO_BOX(combo), 0);
		gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(dialog))), combo);
		gtk_widget_show_all(dialog);
		gint response = gtk_dialog_run(GTK_DIALOG(dialog));
		gint selected = gtk_combo_box_get_active(GTK_COMBO_BOX(combo));
		if (response == GTK_RESPONSE_ACCEPT && selected >= 0 && (guint)selected < certs->len) {
			EitaasPkcs11Certificate *choice = g_ptr_array_index(certs, selected);
			GError *error = NULL;
			GTlsCertificate *cert = g_tls_certificate_new_from_pkcs11_uris(
				choice->certificate_uri, choice->private_key_uri, &error);
			if (cert) {
				WebKitCredential *credential = webkit_credential_new_for_certificate(
					cert, WEBKIT_CREDENTIAL_PERSISTENCE_NONE);
				webkit_authentication_request_authenticate(request, credential);
				webkit_credential_free(credential);
				g_object_unref(cert);
			} else {
				webkit_authentication_request_cancel(request);
			}
			g_clear_error(&error);
		} else {
			webkit_authentication_request_cancel(request);
		}
		gtk_widget_destroy(dialog);
		g_ptr_array_unref(certs);
		return TRUE;
	}
	if (scheme == WEBKIT_AUTHENTICATION_SCHEME_CLIENT_CERTIFICATE_PIN_REQUESTED) {
		GtkWidget *dialog = gtk_dialog_new_with_buttons(
			"Smart-card PIN", parent, GTK_DIALOG_MODAL, "Cancel", GTK_RESPONSE_CANCEL,
			"Continue", GTK_RESPONSE_ACCEPT, NULL);
		GtkWidget *entry = gtk_entry_new();
		gtk_entry_set_visibility(GTK_ENTRY(entry), FALSE);
		gtk_entry_set_input_purpose(GTK_ENTRY(entry), GTK_INPUT_PURPOSE_PIN);
		gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(dialog))), entry);
		gtk_widget_show_all(dialog);
		if (gtk_dialog_run(GTK_DIALOG(dialog)) == GTK_RESPONSE_ACCEPT) {
			WebKitCredential *credential = webkit_credential_new_for_certificate_pin(
				gtk_entry_get_text(GTK_ENTRY(entry)), WEBKIT_CREDENTIAL_PERSISTENCE_NONE);
			webkit_authentication_request_authenticate(request, credential);
			webkit_credential_free(credential);
			gtk_entry_set_text(GTK_ENTRY(entry), "");
		} else {
			webkit_authentication_request_cancel(request);
		}
		gtk_widget_destroy(dialog);
		return TRUE;
	}
	return FALSE;
}
