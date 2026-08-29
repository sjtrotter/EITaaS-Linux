%global webview_commit 2a0a1303c5e8c9c5b73fa9e461739042ebdabe6f
%global debug_package %{nil}

Name:           eitaas-freerdp-webview
Version:        3.31.0
Release:        0.1%{?dist}
Summary:        Isolated FreeRDP WebView prototype for EITaaS
License:        Apache-2.0 AND MIT
URL:            https://github.com/FreeRDP/FreeRDP
Source0:        https://github.com/FreeRDP/FreeRDP/archive/refs/tags/%{version}.tar.gz
Source1:        https://github.com/akallabeth/webview/archive/%{webview_commit}/webview-%{webview_commit}.tar.gz
Patch0:         0001-redact-webview-callback-errors.patch

BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  ninja-build
BuildRequires:  json-c-devel
BuildRequires:  krb5-devel
BuildRequires:  libicu-devel
BuildRequires:  openssl-devel
BuildRequires:  pcsc-lite-devel
BuildRequires:  sso-mib-devel
BuildRequires:  SDL3-devel
BuildRequires:  SDL3_image-devel
BuildRequires:  SDL3_ttf-devel
BuildRequires:  gtk3-devel
BuildRequires:  webkit2gtk4.1-devel

Requires:       pcsc-lite

%description
Experimental SDL FreeRDP client with an embedded AAD WebView. It installs with
private FreeRDP libraries in its own libexec directory and does not replace
the Fedora FreeRDP packages. This package is not release-ready until the CAC
and Azure Government hardware gates in EITaaS-Linux issue 27 pass.

%prep
%autosetup -n FreeRDP-%{version} -p1 -a 1
mkdir -p external
mv webview-%{webview_commit} external/webview

%build
%cmake -G Ninja \
  -DCMAKE_INSTALL_PREFIX=%{_libexecdir}/eitaas-freerdp \
  -DCMAKE_INSTALL_LIBDIR=lib64 \
  -DWITH_AAD=ON \
  -DWITH_CLIENT=ON \
  -DWITH_CLIENT_SDL=ON \
  -DWITH_WEBVIEW=ON \
  -DWITH_PCSC=ON \
  -DWITH_SSO_MIB=ON \
  -DWITH_EMBEDDED_CLI_IN_RDP_FILES=OFF \
  -DWITH_FUSE=OFF \
  -DWITH_SERVER=OFF \
  -DWITH_SAMPLE=OFF \
  -DWITH_X11=OFF \
  -DWITH_WAYLAND=OFF \
  -DWITH_WINPR_TOOLS=OFF \
  -DWITH_MANPAGES=OFF \
  -DWITH_DOCUMENTATION=OFF \
  -DWITH_SWSCALE=OFF \
  -DWITH_CAIRO=OFF \
  -DWITH_FFMPEG=OFF \
  -DWITH_CUPS=OFF \
  -DWITH_PULSE=OFF \
  -DWITH_ALSA=OFF \
  -DWITH_JPEG=OFF \
  -DWITH_GSM=OFF \
  -DWITH_FAAC=OFF \
  -DWITH_FAAD2=OFF \
  -DWITH_LAME=OFF \
  -DWITH_OPENH264=OFF \
  -DWITH_X264=OFF
%cmake_build

%install
%cmake_install
rm -rf %{buildroot}%{_libexecdir}/eitaas-freerdp/include
rm -rf %{buildroot}%{_libexecdir}/eitaas-freerdp/lib64/cmake
rm -rf %{buildroot}%{_libexecdir}/eitaas-freerdp/lib64/pkgconfig
rm -f %{buildroot}%{_libexecdir}/eitaas-freerdp/lib64/*.so
%{__strip} %{buildroot}%{_libexecdir}/eitaas-freerdp/bin/sdl-freerdp
%{__strip} %{buildroot}%{_libexecdir}/eitaas-freerdp/lib64/*.so.3.31.0

%check
client=%{buildroot}%{_libexecdir}/eitaas-freerdp/bin/sdl-freerdp
test -x "$client"
config=$("$client" /buildconfig)
for feature in AAD PCSC SSO_MIB WEBVIEW; do
  test "${config#*WITH_${feature}=ON}" != "$config"
done

%files
%license LICENSE
%doc README.md
%{_libexecdir}/eitaas-freerdp/bin/sdl-freerdp
%{_libexecdir}/eitaas-freerdp/lib64/libfreerdp-client3.so.3*
%{_libexecdir}/eitaas-freerdp/lib64/libfreerdp3.so.3*
%{_libexecdir}/eitaas-freerdp/lib64/libwinpr3.so.3*

%changelog
* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 3.31.0-0.1
- Initial isolated WebView prototype
