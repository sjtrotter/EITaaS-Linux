#pragma once

#include <webkit2/webkit2.h>

gboolean eitaas_webview_authenticate(WebKitWebView *web_view,
                                     WebKitAuthenticationRequest *request,
                                     gpointer parent_data);
