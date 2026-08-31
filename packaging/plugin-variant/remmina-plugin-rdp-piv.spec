# remmina-plugin-rdp-piv — drop-in AAD + smart card (PIV) RDP plugin (issue #101).
#
# A drop-in replacement for the stock/base remmina-plugins-rdp that adds the
# Azure AD (Entra) embedded web sign-in and the PKCS #11 smart-card (PIV)
# certificate picker + PIN entry during that sign-in. It is built from the
# SAME pinned Remmina 1.4.43 source (030946c8) as the companion base
# remmina.spec, so the plugin is ABI-matched to that Remmina, and is linked
# against the distribution's own FreeRDP 3 (>= 3.16 required for the AVD gateway
# APIs; Fedora 44 ships 3.30.0). It carries the EITaaS downstream patch series
# and compiles WITH_RDP_AUTH_AAD=ON / WITH_SSO_MIB=OFF (WebKit browser path
# only; no SSO-MIB identity broker). See docs/plugin-variant-testing.md and
# ADR-0003.
#
# The only file installed is the patched remmina-plugin-rdp.so. The RDP emblem
# icons are already shipped by the core `remmina` package, so nothing else is
# needed for a clean swap.

%global commit 030946c83fe1b7218a21b6d32f9c975b243b7031
# EVR of the base remmina this plugin is ABI-matched to and requires exactly.
%global base_version 1.4.43
%global base_release 1%{?dist}
# The remmina-plugins-rdp capability EVR this package provides/obsoletes. It is
# one release above the base plugin (1.4.43-1) so a plain `dnf install` of this
# package automatically obsoletes BOTH Fedora's stock plugin (1.4.41-2) and the
# equal-versioned base plugin (1.4.43-1) without needing --allowerasing, while
# never obsoleting its own provide.
%global rdp_evr 1.4.43-2%{?dist}

Name: remmina-plugin-rdp-piv
Version: %{base_version}
Release: 1%{?dist}
Summary: Drop-in Remmina RDP plugin with Azure AD + smart card (PIV) web sign-in
# Remmina (GPL-2.0-or-later, OpenSSL exception) + EITaaS smart-card integration
# (GPL-2.0-or-later). MIT covers the separately shipped EITaaS launcher/CLI,
# which this package does not contain.
License: GPL-2.0-or-later
URL: https://github.com/sjtrotter/EITaaS-Linux

# Same pinned Remmina 1.4.43 snapshot as the base remmina.spec
# (sha256 8976850314dddab8cfe74f413233a712e7ba4b6ccf72b56cbf635b51f1ea2801,
# recorded in packaging/remmina/sources.json).
Source0: https://gitlab.com/Remmina/Remmina/-/archive/%{commit}/Remmina-%{commit}.tar.gz

# EITaaS smart-card (PIV) WebKit authentication, compiled into the RDP plugin.
Source1: eitaas_smartcard_auth.c
Source2: eitaas_smartcard_auth.h
# Notices for the composite artifact.
Source3: THIRD_PARTY_NOTICES.md

# EITaaS downstream RDP patch series (must match packaging/remmina/*.patch and
# the upstream/remmina equivalents; a change to one must be applied to all).
Patch0: 0001-preserve-protected-rdpw-settings.patch
Patch1: 0002-add-smartcard-webview-authentication.patch
Patch2: 0003-keep-private-runtime-paths.patch
Patch3: 0004-use-profile-avd-scope.patch
Patch4: 0005-bind-protected-rdpw-content.patch
Patch5: 0006-Harden-RDPW-and-OAuth-transaction-boundaries.patch
Patch6: 0007-extend-arm-configuration-timeout.patch

BuildRequires: cmake >= 3.2
BuildRequires: gcc-c++
BuildRequires: gettext
BuildRequires: intltool
BuildRequires: pkgconfig(freerdp3) >= 3.16.0
BuildRequires: pkgconfig(gtk+-3.0)
BuildRequires: pkgconfig(json-glib-1.0)
BuildRequires: pkgconfig(libsecret-1)
BuildRequires: pkgconfig(libsoup-3.0)
BuildRequires: pkgconfig(libssh) >= 0.8.0
BuildRequires: pkgconfig(libpcre2-8)
BuildRequires: pkgconfig(webkit2gtk-4.1)
BuildRequires: pkgconfig(x11)
BuildRequires: pkgconfig(xkbfile)
BuildRequires: pkgconfig(libcurl)
BuildRequires: binutils

# ABI lock: the plugin is compiled against this exact Remmina build (matching
# the stock plugins-rdp's own "Requires: remmina = EVR"); a different remmina
# build may change the plugin ABI, so pin the full EVR.
Requires: remmina%{?_isa} = %{base_version}-%{base_release}

# Clean drop-in swap of the stock/base RDP plugin. Provides satisfies remmina's
# "Recommends: remmina-plugins-rdp"; Obsoletes (at rdp_evr = 1.4.43-2, one above
# the base plugin) auto-removes both Fedora's stock plugin and the equal-EVR
# base plugin on `dnf install`; Conflicts is belt-and-suspenders against manual
# co-installation.
Provides: remmina-plugins-rdp = %{rdp_evr}
Provides: remmina-plugins-rdp%{?_isa} = %{rdp_evr}
Obsoletes: remmina-plugins-rdp < %{rdp_evr}
Conflicts: remmina-plugins-rdp

# Smart-card sign-in runtime helpers (the plugin builds and every non-PIV
# connection works without them):
#   p11tool lists the card's certificates (searched in PATH at run time);
#   opensc provides the PKCS #11 module registered with p11-kit.
Recommends: gnutls-utils
Recommends: opensc

%description
%{summary}.

This is a drop-in replacement for the stock Remmina RDP plugin
(remmina-plugins-rdp) that adds Azure Virtual Desktop / Entra (Azure AD)
authentication with an embedded WebKit sign-in window, and a PKCS #11
smart-card (PIV) client-certificate picker and PIN entry inside that window.
It imports signed AVD .rdpw profiles, selects the Azure US Government
authority/scope/redirect, and binds the OAuth transaction (state + PKCE S256,
exact redirect). Certificate verification stays on; no PINs, tokens, PKCS #11
URIs, or card labels are logged.

It is built from the same pinned Remmina 1.4.43 source as the base `remmina`
package and links the distribution's FreeRDP 3 and WebKit2GTK 4.1.

%prep
%autosetup -p1 -n Remmina-%{commit}
# Compiled into the RDP plugin by the 0002 patch (#include of the .c).
cp -p %{SOURCE1} %{SOURCE2} plugins/rdp/
cp -p %{SOURCE3} .

%build
# Same base flags as the vanilla remmina build, plus the AAD + PIV web sign-in
# (WITH_SSO_MIB=OFF: WebKit browser path only). Only the RDP plugin is built.
%cmake \
    -DCMAKE_INSTALL_LIBDIR=%{_lib} \
    -DCMAKE_INSTALL_PREFIX=%{_prefix} \
    -DWITH_FREERDP3=ON \
    -DWITH_RDP=ON \
    -DWITH_RDP_AUTH_AAD=ON \
    -DWITH_SSO_MIB=OFF \
    -DWITH_GETTEXT=ON \
    -DWITH_NEWS=OFF \
    -DWITH_KIOSK_SESSION=OFF
%cmake_build --target remmina-plugin-rdp

%install
install -d %{buildroot}%{_libdir}/remmina/plugins
install -p -m 0755 \
    %{_vpath_builddir}/plugins/rdp/remmina-plugin-rdp.so \
    %{buildroot}%{_libdir}/remmina/plugins/remmina-plugin-rdp.so

%check
so=%{buildroot}%{_libdir}/remmina/plugins/remmina-plugin-rdp.so
echo "== NEEDED libraries =="
readelf -d "$so" | grep NEEDED
readelf -d "$so" | grep -q 'libfreerdp3.so.3'   || { echo "FAIL: not linked to libfreerdp3.so.3"; exit 1; }
readelf -d "$so" | grep -q 'libwebkit2gtk-4.1'  || { echo "FAIL: not linked to libwebkit2gtk-4.1"; exit 1; }
echo "== smart-card auth strings =="
strings "$so" | grep -q 'smartcard-auth:'                    || { echo "FAIL: missing smartcard-auth reason codes"; exit 1; }
strings "$so" | grep -q 'p11tool'                            || { echo "FAIL: missing p11tool reference"; exit 1; }
strings "$so" | grep -qi 'g_tls_certificate_new_from_pkcs11' || { echo "FAIL: missing PKCS#11 certificate handling"; exit 1; }
echo "OK: linkage and smart-card strings present"

%files
%license LICENSE
%doc THIRD_PARTY_NOTICES.md
%{_libdir}/remmina/plugins/remmina-plugin-rdp.so

%changelog
* Mon Aug 31 2026 EITaaS-Linux <noreply@example.invalid> - 1.4.43-1
- Initial drop-in AAD/PIV RDP plugin variant (issue #101, ADR-0003 Track 2).
- Built from the pinned Remmina 1.4.43 snapshot 030946c8 with the EITaaS
  downstream RDP series, WITH_RDP_AUTH_AAD=ON / WITH_SSO_MIB=OFF, against the
  distribution FreeRDP 3.30 and WebKit2GTK 4.1.
- Provides/Obsoletes/Conflicts remmina-plugins-rdp for a clean swap.
