// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 Stephen Trotter
//
// Behavioral test for PKCS #11 certificate discovery in eitaas_cac_auth.c,
// driven by a fake p11tool (a shell script compiled in as PKCS11_TOOL).
// Issue #82: p11tool exits non-zero for a token without matching objects
// (p11-kit's trust tokens come first), which used to abort discovery before
// the smart card was ever queried. Compiled and run by
// tests/test_remmina_packaging.py when a C compiler and WebKitGTK
// development files are available.

#include <glib.h>
#define REMMINA_PLUGIN_DEBUG(fmt, ...) g_debug(fmt, ##__VA_ARGS__)
#define REMMINA_PLUGIN_WARNING(fmt, ...) g_warning(fmt, ##__VA_ARGS__)

#include "../../packaging/remmina/eitaas_cac_auth.c"

#include <stdio.h>

static int check(gboolean condition, const char *what)
{
	if (!condition)
		fprintf(stderr, "FAIL: %s\n", what);
	return condition ? 0 : 1;
}

int main(void)
{
	int failures = 0;
	EitaasDiscoveryStats stats = { 0 };
	GError *error = NULL;

	/* Trust token first, then an empty token, then the PIV token. */
	g_setenv("FAKE_P11TOOL_MODE", "piv", TRUE);
	GPtrArray *certs = enumerate_certificates(NULL, &stats, &error);
	failures += check(error == NULL, "discovery succeeds despite an empty token");
	if (error)
		fprintf(stderr, "  error: %s\n", error->message);
	failures += check(stats.tokens == 3, "three tokens listed");
	failures += check(stats.trust_skipped == 1, "the p11-kit trust token is skipped without a query");
	failures += check(stats.empty_tokens == 1, "the empty token is counted, not fatal");
	failures += check(stats.last_empty_status == 1, "the empty token's exit status is recorded");
	failures += check(stats.certificates == 4, "all four PIV certificates are read from the smart card");
	failures += check(stats.kept == 2 && stats.dropped == 2,
	                  "PIV Authentication and Card Authentication pass the label filter");
	failures += check(certs->len == 2, "two selectable certificates");
	g_ptr_array_unref(certs);
	g_clear_error(&error);

	/* A token listing failure stays fatal. */
	memset(&stats, 0, sizeof(stats));
	g_setenv("FAKE_P11TOOL_MODE", "tokens-fail", TRUE);
	certs = enumerate_certificates(NULL, &stats, &error);
	failures += check(error != NULL, "token listing failure is an error");
	failures += check(certs->len == 0, "no certificates after a token listing failure");
	g_ptr_array_unref(certs);
	g_clear_error(&error);

	/* Non-zero exit together with URL output is malformed and fatal. */
	memset(&stats, 0, sizeof(stats));
	g_setenv("FAKE_P11TOOL_MODE", "malformed", TRUE);
	certs = enumerate_certificates(NULL, &stats, &error);
	failures += check(error != NULL, "URLs with a non-zero exit status are rejected");
	g_ptr_array_unref(certs);
	g_clear_error(&error);

	/* A tool killed by a signal is never an empty token. */
	memset(&stats, 0, sizeof(stats));
	g_setenv("FAKE_P11TOOL_MODE", "signal", TRUE);
	certs = enumerate_certificates(NULL, &stats, &error);
	failures += check(error != NULL && strstr(error->message, "signal") != NULL,
	                  "signal death of p11tool is a discovery error");
	failures += check(stats.empty_tokens == 1, "the empty token before the PIV token is still counted");
	g_ptr_array_unref(certs);
	g_clear_error(&error);

	/* Only empty tokens: no error, zero certificates (the "no usable" dialog path). */
	memset(&stats, 0, sizeof(stats));
	g_setenv("FAKE_P11TOOL_MODE", "all-empty", TRUE);
	certs = enumerate_certificates(NULL, &stats, &error);
	failures += check(error == NULL && certs->len == 0, "all-empty tokens yield zero certificates without error");
	failures += check(stats.empty_tokens == 1 && stats.trust_skipped == 1, "empty token counted, trust token skipped");
	g_ptr_array_unref(certs);
	g_clear_error(&error);
	return failures ? 1 : 0;
}
