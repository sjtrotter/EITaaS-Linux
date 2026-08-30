%global freerdp_version 3.31.0
%global remmina_commit 030946c83fe1b7218a21b6d32f9c975b243b7031
%global debug_package %{nil}

Name:           eitaas-remmina
Version:        1.4.43
Release:        0.8%{?dist}
Summary:        Isolated Remmina AVD and CAC prototype for EITaaS
License:        GPL-2.0-or-later AND Apache-2.0 AND MIT
URL:            https://gitlab.com/Remmina/Remmina
Source0:        https://github.com/FreeRDP/FreeRDP/archive/refs/tags/%{freerdp_version}.tar.gz
Source1:        https://gitlab.com/Remmina/Remmina/-/archive/%{remmina_commit}/Remmina-%{remmina_commit}.tar.gz
Source2:        eitaas_cac_auth.c
Source3:        eitaas_cac_auth.h
Source4:        eitaas-remmina
Source5:        EITaaS-LICENSE
Source6:        THIRD_PARTY_NOTICES.md
Source7:        sources.json
Patch0:         0001-preserve-protected-rdpw-settings.patch
Patch1:         0002-add-cac-webview-authentication.patch
Patch2:         0003-keep-private-runtime-paths.patch
Patch3:         0004-use-profile-avd-scope.patch
Patch4:         0005-bind-protected-rdpw-content.patch

BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  ninja-build
BuildRequires:  gtk3-devel
BuildRequires:  json-c-devel
BuildRequires:  json-glib-devel
BuildRequires:  krb5-devel
BuildRequires:  libcurl-devel
BuildRequires:  libicu-devel
BuildRequires:  libsecret-devel
BuildRequires:  libsodium-devel
BuildRequires:  libsoup3-devel
BuildRequires:  libssh-devel
BuildRequires:  openssl-devel
BuildRequires:  pcsc-lite-devel
BuildRequires:  sso-mib-devel
BuildRequires:  webkit2gtk4.1-devel

Requires:       gnutls-utils
Requires:       pcsc-lite

%description
Experimental private Remmina and FreeRDP build for protected Azure Virtual
Desktop RDPW profiles, embedded Azure Government CAC authentication, and
smart-card redirection. It does not replace distribution Remmina or FreeRDP.

%prep
%setup -q -n FreeRDP-%{freerdp_version} -a 1
remmina=Remmina-%{remmina_commit}
cp %{SOURCE2} "$remmina/plugins/rdp/eitaas_cac_auth.c"
cp %{SOURCE3} "$remmina/plugins/rdp/eitaas_cac_auth.h"
patch --fuzz=0 -p1 -d "$remmina" < %{PATCH0}
patch --fuzz=0 -p1 -d "$remmina" < %{PATCH1}
patch --fuzz=0 -p1 -d "$remmina" < %{PATCH2}
patch --fuzz=0 -p1 -d "$remmina" < %{PATCH3}

%build
prefix=%{_libexecdir}/eitaas-remmina
private_root="$PWD/private-root"
cmake -S . -B freerdp-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_INSTALL_LIBDIR=lib64 \
  -DWITH_AAD=ON -DWITH_PCSC=ON -DWITH_SSO_MIB=ON -DWITH_CLIENT=ON \
  -DWITH_CLIENT_SDL=OFF -DWITH_X11=OFF -DWITH_WAYLAND=OFF -DWITH_SERVER=OFF \
  -DWITH_SAMPLE=OFF -DWITH_MANPAGES=OFF -DWITH_DOCUMENTATION=OFF -DWITH_FUSE=OFF \
  -DWITH_CUPS=OFF -DWITH_FFMPEG=OFF -DWITH_SWSCALE=OFF -DWITH_CAIRO=OFF \
  -DWITH_ALSA=OFF -DWITH_PULSE=OFF -DWITH_JPEG=OFF -DWITH_GSM=OFF \
  -DWITH_LAME=OFF -DWITH_OPENH264=OFF
cmake --build freerdp-build --parallel 1
DESTDIR="$private_root" cmake --install freerdp-build

cmake -S Remmina-%{remmina_commit} -B remmina-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
  -DCMAKE_PREFIX_PATH="$private_root$prefix" \
  -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
  -DCMAKE_INSTALL_RPATH='$ORIGIN/../lib64:$ORIGIN/../..' \
  -DWITH_FREERDP3=ON -DWITH_RDP_AUTH_AAD=ON -DWITH_SSO_MIB=ON \
  -DWITH_GCRYPT=OFF -DWITH_VTE=OFF -DHAVE_LIBAPPINDICATOR=OFF \
  -DWITH_LIBVNCSERVER=OFF -DWITH_SPICE=OFF -DWITH_NEWS=OFF -DWITH_STATS=OFF \
  -DWITH_TIP=OFF -DWITH_MANPAGES=OFF -DWITH_ICON_CACHE=OFF -DWITH_WWW=OFF \
  -DWITH_GVNC=OFF -DWITH_X2GO=OFF -DWITH_KF5WALLET=OFF -DWITH_ST=OFF \
  -DWITH_XDMCP=OFF -DWITH_NX=OFF
cmake --build remmina-build --parallel 1

%install
prefix=%{_libexecdir}/eitaas-remmina
DESTDIR=%{buildroot} cmake --install freerdp-build
DESTDIR=%{buildroot} cmake --install remmina-build
install -Dpm0755 %{SOURCE4} %{buildroot}%{_bindir}/eitaas-remmina
license_dir=%{buildroot}%{_licensedir}/%{name}
install -Dpm0644 LICENSE "$license_dir/FreeRDP-LICENSE"
install -Dpm0644 winpr/libwinpr/sysinfo/cpufeatures/NOTICE \
  "$license_dir/FreeRDP-cpufeatures-NOTICE"
install -Dpm0644 Remmina-%{remmina_commit}/COPYING "$license_dir/Remmina-COPYING"
install -Dpm0644 Remmina-%{remmina_commit}/LICENSE "$license_dir/Remmina-LICENSE"
install -Dpm0644 Remmina-%{remmina_commit}/LICENSE.OpenSSL \
  "$license_dir/Remmina-LICENSE.OpenSSL"
install -Dpm0644 %{SOURCE5} "$license_dir/EITaaS-LICENSE"
install -Dpm0644 %{SOURCE6} "$license_dir/THIRD_PARTY_NOTICES.md"
install -Dpm0644 %{SOURCE7} %{buildroot}%{_docdir}/%{name}/sources.json
rm -rf %{buildroot}$prefix/include %{buildroot}$prefix/lib64/cmake \
       %{buildroot}$prefix/lib64/pkgconfig %{buildroot}$prefix/share/man
rm -f %{buildroot}$prefix/lib64/*.so

%check
plugin=%{buildroot}%{_libexecdir}/eitaas-remmina/lib64/remmina/plugins/remmina-plugin-rdp.so
test -x %{buildroot}%{_libexecdir}/eitaas-remmina/bin/remmina
test -f "$plugin"
grep -a -q 'Could not load the protected RDPW profile' "$plugin"
grep -a -q 'Select smart-card authentication certificate' "$plugin"
license_dir=%{buildroot}%{_licensedir}/%{name}
test -s "$license_dir/FreeRDP-LICENSE"
test -s "$license_dir/FreeRDP-cpufeatures-NOTICE"
test -s "$license_dir/Remmina-COPYING"
test -s "$license_dir/Remmina-LICENSE"
test -s "$license_dir/Remmina-LICENSE.OpenSSL"
test -s "$license_dir/EITaaS-LICENSE"
test -s "$license_dir/THIRD_PARTY_NOTICES.md"
test -s %{buildroot}%{_docdir}/%{name}/sources.json
grep -q 'Apache License' "$license_dir/FreeRDP-LICENSE"
grep -q 'special exception' "$license_dir/Remmina-COPYING"
grep -q 'GNU GENERAL PUBLIC LICENSE' "$license_dir/Remmina-LICENSE"
grep -q 'OpenSSL License' "$license_dir/Remmina-LICENSE.OpenSSL"
grep -q 'MIT License' "$license_dir/EITaaS-LICENSE"

%files
%license %{_licensedir}/%{name}
%doc %{_docdir}/%{name}/sources.json
%{_bindir}/eitaas-remmina
%{_libexecdir}/eitaas-remmina

%changelog
* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.8
- Ship the shared pinned-source manifest used by native packaging formats

* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.7
- Install distinct EITaaS, Remmina, FreeRDP, and bundled-component notices
- Document component licensing and verify corresponding sources in package checks

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.6
- Quit the isolated application when one-shot CAC authentication is cancelled

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.5
- End the AVD authentication attempt when CAC discovery is cancelled

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.4
- Discover CAC certificates off the GTK main thread

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.3
- Use the registered AVD native-client callback for government profiles

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.2
- Select Azure Government authority and scope for government RDPW profiles

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.4.43-0.1
- Initial isolated protected-RDPW and CAC authentication prototype
