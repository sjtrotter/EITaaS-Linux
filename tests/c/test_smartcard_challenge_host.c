// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 Stephen Trotter
//
// Behavioral test for the client-certificate challenge-host relationship in
// eitaas_smartcard_auth.c. Trailing-dot and IDNA/Unicode host forms are not
// normalised by the helper and must fail closed. Compiled and run by tests/test_remmina_packaging.py when
// a C compiler and WebKitGTK development files are available.

// The source is normally included into rdp_web_auth.c, where Remmina's plugin
// service provides these; the harness routes them to GLib's log domain.
#include <glib.h>
#define REMMINA_PLUGIN_DEBUG(fmt, ...) g_debug(fmt, ##__VA_ARGS__)
#define REMMINA_PLUGIN_WARNING(fmt, ...) g_warning(fmt, ##__VA_ARGS__)

#include "../../packaging/remmina/eitaas_smartcard_auth.c"

#include <stdio.h>

typedef struct {
	const gchar *authority;
	const gchar *host;
	gboolean expected;
} HostCase;

static const HostCase cases[] = {
	{ "login.microsoftonline.us", "login.microsoftonline.us", TRUE },
	{ "login.microsoftonline.us", "certauth.login.microsoftonline.us", TRUE },
	{ "login.microsoftonline.us", "CertAuth.Login.MicrosoftOnline.US", TRUE },
	{ "login.microsoftonline.com", "certauth.login.microsoftonline.com", TRUE },
	{ "login.microsoftonline.us", "certauth.login.microsoftonline.us.evil", FALSE },
	{ "login.microsoftonline.us", "xcertauth.login.microsoftonline.us", FALSE },
	{ "login.microsoftonline.us", "certauth.certauth.login.microsoftonline.us", FALSE },
	{ "login.microsoftonline.us", "certauth.login.microsoftonline.com", FALSE },
	{ "login.microsoftonline.us", "login.microsoftonline.com", FALSE },
	{ "login.microsoftonline.us", "evil.login.microsoftonline.us", FALSE },
	{ "login.microsoftonline.us", "certauth.", FALSE },
	{ "login.microsoftonline.us", "login.microsoftonline.us.", FALSE },
	{ "login.microsoftonline.us", "certauth.login.microsoftonline.us.", FALSE },
	{ "LOGIN.MICROSOFTONLINE.US", "certauth.login.microsoftonline.us", TRUE },
	{ "LOGIN.MICROSOFTONLINE.US", "login.microsoftonline.us", TRUE },
	{ "login.microsoftonline.us", "", FALSE },
};

int main(void)
{
	int failures = 0;
	for (gsize i = 0; i < G_N_ELEMENTS(cases); i++) {
		gboolean actual = host_is_authority_or_certauth(cases[i].host, cases[i].authority);
		if (actual != cases[i].expected) {
			failures++;
			fprintf(stderr, "FAIL: authority=%s host=%s expected=%d actual=%d\n",
			        cases[i].authority, cases[i].host, cases[i].expected, actual);
		}
	}
	if (g_strcmp0(CERTAUTH_HOST_PREFIX, "certauth.") != 0) {
		failures++;
		fprintf(stderr, "FAIL: unexpected CERTAUTH_HOST_PREFIX\n");
	}
	return failures ? 1 : 0;
}
