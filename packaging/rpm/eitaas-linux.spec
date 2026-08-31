%global manifest packaging/remmina/sources.json
# The canonical (PEP 440) version from pyproject.toml. It names the release
# tag, the source tarball, and its top-level directory. RPM's Version below is
# the distribution spelling of the same release: a pre-release marker becomes
# a `~` segment so X.Y.Z~rcN sorts BELOW the eventual X.Y.Z final and the
# final upgrades over its candidates (issue #95). For a final release the two
# strings are identical. scripts/check-version-consistency.py guards the pair.
%global upstream_version 1.0.0rc1
%global freerdp_version 3.30.0
%global remmina_version 1.4.43
%global remmina_commit 030946c83fe1b7218a21b6d32f9c975b243b7031
%global private_prefix %{_libexecdir}/eitaas-remmina
# No separate debuginfo package is produced for this prototype: the private
# prefix ships the release binaries as built, unstripped.
%global debug_package %{nil}

Name:           eitaas-linux
Version:        1.0.0~rc1
Release:        1%{?dist}
Summary:        EITaaS Azure Virtual Desktop client, diagnostics, and helper GUI
# The package is a composite: Remmina and the EITaaS smart card (PIV)
# integration compiled into its RDP plugin are GPL-2.0-or-later, FreeRDP is
# Apache-2.0, and the EITaaS Python tooling and launcher are MIT. See
# THIRD_PARTY_NOTICES.md.
License:        GPL-2.0-or-later AND Apache-2.0 AND MIT
URL:            https://github.com/sjtrotter/EITaaS-Linux
Source0:        https://github.com/sjtrotter/EITaaS-Linux/archive/refs/tags/v%{upstream_version}.tar.gz
Source1:        https://github.com/FreeRDP/FreeRDP/archive/refs/tags/%{freerdp_version}.tar.gz
Source2:        https://gitlab.com/Remmina/Remmina/-/archive/%{remmina_commit}/Remmina-%{remmina_commit}.tar.gz

BuildRequires:  libusb1-devel
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-wheel
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  gettext
BuildRequires:  ninja-build
BuildRequires:  patch
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
BuildRequires:  webkit2gtk4.1-devel
BuildRequires:  zlib-devel

Requires:       python3
Requires:       gnutls-utils
Requires:       opensc
Requires:       pcsc-lite
Requires:       pcsc-lite-ccid
Requires:       pcsc-tools
# The GUI loads GTK 4 and Libadwaita through GObject introspection; Fedora has
# no typelib() provides and no automatic generator for PyGObject imports, so
# the library packages are required explicitly (rpmlint's
# explicit-lib-dependency is filtered in eitaas-linux.rpmlintrc).
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita

# Issue #80: one package replaces the former split. The bundled client was
# eitaas-remmina <= %%{remmina_version}-0.15 and the GUI was eitaas-linux-gui
# < %%{version}-%%{release}; the matching Provides are one revision above each
# Obsoletes bound so this package never obsoletes itself.
# %%{remmina_version} is the bundled Remmina pin, and the retired package
# used it as its own version. If the bundle is ever re-pinned, both lines
# below must keep covering 1.4.43-0.15, the last release that shipped.
Obsoletes:      eitaas-remmina < %{remmina_version}-1
Provides:       eitaas-remmina = %{remmina_version}-1
Obsoletes:      eitaas-linux-gui < %{version}-%{release}
Provides:       eitaas-linux-gui = %{version}-%{release}

%description
Everything needed to reach an EITaaS Azure Virtual Desktop workspace with
smart card (PIV) redirection: the isolated one-shot Remmina and FreeRDP
client built from the pins in sources.json and installed under a private
prefix, the eitaas-remmina launcher, the eitaas command-line diagnostics, and
the EITaaS Connect GTK 4 helper. The private client does not replace the
distribution Remmina or FreeRDP packages.

%prep
%setup -q -n eitaas-linux-%{upstream_version} -a 1 -a 2
remmina=Remmina-%{remmina_commit}
cp packaging/remmina/eitaas_smartcard_auth.c "$remmina/plugins/rdp/eitaas_smartcard_auth.c"
cp packaging/remmina/eitaas_smartcard_auth.h "$remmina/plugins/rdp/eitaas_smartcard_auth.h"
# sources.json owns the ordered patch series; the spec never repeats it.
for patch in $(%{python3} -c 'import json,sys;print("\n".join(json.load(open(sys.argv[1]))["patches"]))' %{manifest}); do
  patch --fuzz=0 -p1 -d "$remmina" < "packaging/remmina/$patch"
done

%build
%pyproject_wheel

private_root="$PWD/private-root"
cmake -S FreeRDP-%{freerdp_version} -B freerdp-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="%{private_prefix}" \
  -DCMAKE_INSTALL_LIBDIR=lib64 \
  -DWITH_AAD=ON -DWITH_PCSC=ON -DWITH_SSO_MIB=OFF -DWITH_CLIENT=ON \
  -DWITH_CLIENT_SDL=OFF -DWITH_X11=OFF -DWITH_WAYLAND=OFF -DWITH_SERVER=OFF \
  -DWITH_SAMPLE=OFF -DWITH_MANPAGES=OFF -DWITH_DOCUMENTATION=OFF -DWITH_FUSE=OFF \
  -DWITH_CUPS=OFF -DWITH_FFMPEG=OFF -DWITH_SWSCALE=OFF -DWITH_CAIRO=OFF \
  -DWITH_ALSA=OFF -DWITH_PULSE=OFF -DWITH_JPEG=OFF -DWITH_GSM=OFF \
  -DWITH_LAME=OFF -DWITH_OPENH264=OFF
cmake --build freerdp-build --parallel 1
DESTDIR="$private_root" cmake --install freerdp-build

cmake -S Remmina-%{remmina_commit} -B remmina-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="%{private_prefix}" \
  -DCMAKE_PREFIX_PATH="$private_root%{private_prefix}" \
  -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
  -DCMAKE_INSTALL_RPATH='$ORIGIN/../lib64:$ORIGIN/../..' \
  -DWITH_FREERDP3=ON -DWITH_RDP_AUTH_AAD=ON -DWITH_SSO_MIB=OFF \
  -DREMMINA_P11TOOL=/usr/bin/p11tool \
  -DWITH_GCRYPT=OFF -DWITH_VTE=OFF -DHAVE_LIBAPPINDICATOR=OFF \
  -DWITH_CUPS=OFF -DWITH_AVAHI=OFF \
  -DWITH_LIBVNCSERVER=OFF -DWITH_SPICE=OFF -DWITH_NEWS=OFF -DWITH_STATS=OFF \
  -DWITH_TIP=OFF -DWITH_MANPAGES=OFF -DWITH_ICON_CACHE=OFF -DWITH_WWW=OFF \
  -DWITH_GVNC=OFF -DWITH_X2GO=OFF -DWITH_KF5WALLET=OFF -DWITH_ST=OFF \
  -DWITH_XDMCP=OFF -DWITH_NX=OFF -DWITH_PYTHONLIBS=OFF
cmake --build remmina-build --parallel 1

%install
%pyproject_install
%pyproject_save_files eitaas eitaas_gui

DESTDIR=%{buildroot} cmake --install freerdp-build
DESTDIR=%{buildroot} cmake --install remmina-build
install -Dpm 0755 packaging/remmina/eitaas-remmina %{buildroot}%{_bindir}/eitaas-remmina
rm -rf %{buildroot}%{private_prefix}/include %{buildroot}%{private_prefix}/lib64/cmake \
       %{buildroot}%{private_prefix}/lib64/pkgconfig %{buildroot}%{private_prefix}/share/man
rm -f %{buildroot}%{private_prefix}/lib64/*.so

install -Dpm 0644 docs/eitaas.1 %{buildroot}%{_mandir}/man1/eitaas.1
install -Dpm 0644 docs/eitaas-gui.1 %{buildroot}%{_mandir}/man1/eitaas-gui.1
install -Dpm 0644 completions/eitaas.bash %{buildroot}%{_datadir}/bash-completion/completions/eitaas
install -Dpm 0644 completions/_eitaas %{buildroot}%{_datadir}/zsh/site-functions/_eitaas
desktop-file-install --dir=%{buildroot}%{_datadir}/applications data/org.eitaas.Helper.desktop
install -Dpm 0644 data/org.eitaas.Helper.metainfo.xml %{buildroot}%{_metainfodir}/org.eitaas.Helper.metainfo.xml
install -Dpm 0644 data/eitaas-rdpw.xml %{buildroot}%{_datadir}/mime/packages/eitaas-rdpw.xml
install -Dpm 0644 data/icons/hicolor/scalable/apps/org.eitaas.Helper.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.eitaas.Helper.svg
install -Dpm 0644 data/icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg

license_dir=%{buildroot}%{_licensedir}/%{name}
install -Dpm 0644 LICENSE "$license_dir/EITaaS-LICENSE"
install -Dpm 0644 packaging/remmina/THIRD_PARTY_NOTICES.md "$license_dir/THIRD_PARTY_NOTICES.md"
install -Dpm 0644 FreeRDP-%{freerdp_version}/LICENSE "$license_dir/FreeRDP-LICENSE"
install -Dpm 0644 FreeRDP-%{freerdp_version}/winpr/libwinpr/sysinfo/cpufeatures/NOTICE \
  "$license_dir/FreeRDP-cpufeatures-NOTICE"
install -Dpm 0644 Remmina-%{remmina_commit}/COPYING "$license_dir/Remmina-COPYING"
install -Dpm 0644 Remmina-%{remmina_commit}/LICENSE "$license_dir/Remmina-LICENSE"
install -Dpm 0644 Remmina-%{remmina_commit}/LICENSE.OpenSSL \
  "$license_dir/Remmina-LICENSE.OpenSSL"
# The documentation set is installed explicitly rather than through %%doc's
# relative form, which regenerates (and would first delete) the whole
# %%{_docdir}/%%{name} directory after %%install.
doc_dir=%{buildroot}%{_docdir}/%{name}
install -Dpm 0644 %{manifest} "$doc_dir/sources.json"
install -Dpm 0644 README.md "$doc_dir/README.md"
install -Dpm 0644 NOTICE "$doc_dir/NOTICE"
install -Dpm 0644 SECURITY.md "$doc_dir/SECURITY.md"
install -Dpm 0644 SUPPORT.md "$doc_dir/SUPPORT.md"

%check
PYTHONPATH=src %{python3} -m unittest discover -s tests -v
desktop-file-validate %{buildroot}%{_datadir}/applications/org.eitaas.Helper.desktop
# appstreamcli exits non-zero for info-level hints as well as real errors;
# report them without failing the build.
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/org.eitaas.Helper.metainfo.xml || :

plugin=%{buildroot}%{private_prefix}/lib64/remmina/plugins/remmina-plugin-rdp.so
test -x %{buildroot}%{private_prefix}/bin/remmina
test -f "$plugin"
grep -a -q 'The stored connection file holds invalid or disallowed settings.' "$plugin"
grep -a -q 'Select smart-card authentication certificate' "$plugin"
test -x %{buildroot}%{_bindir}/eitaas-remmina
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

# MIME and icon caches are refreshed by Fedora's shared-mime-info and
# hicolor-icon-theme file triggers; no scriptlets are needed.
%files -f %{pyproject_files}
%license %{_licensedir}/%{name}
%doc %{_docdir}/%{name}
%{_bindir}/eitaas
%{_bindir}/eitaas-gui
%{_bindir}/eitaas-remmina
%{private_prefix}
%{_mandir}/man1/eitaas.1*
%{_mandir}/man1/eitaas-gui.1*
%{_datadir}/bash-completion/completions/eitaas
%{_datadir}/zsh/site-functions/_eitaas
%{_datadir}/applications/org.eitaas.Helper.desktop
%{_metainfodir}/org.eitaas.Helper.metainfo.xml
%{_datadir}/mime/packages/eitaas-rdpw.xml
%{_datadir}/icons/hicolor/scalable/apps/org.eitaas.Helper.svg
%{_datadir}/icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg

%changelog
* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 1.0.0~rc1-1
- First 1.0 release candidate: bundled Remmina 1.4.43 + FreeRDP 3.30.0
  client with smart card (PIV) AVD authentication, the eitaas CLI, and the
  EITaaS Connect helper GUI, shipped as one package.

* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.2.0-2
- Restore USB device redirection: build FreeRDP with its default urbdrc
  channel and declare the libusb build dependency on every distribution
* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.2.0-1
- Ship one eitaas-linux package containing the bundled Remmina/FreeRDP client,
  the command-line helper, and the GTK 4 helper GUI
- Obsolete the former eitaas-remmina and eitaas-linux-gui packages

* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-7
- Redact HTTP bearer values (any casing), quoted JSON token fields, and
  Set-Cookie/ARRAffinity cookie values from session logs

* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-6
- Show the diagnostic log whenever a smart-card stage warned, even on exit 0

* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-5
- Capture the client's output into a redacted per-session log
- Show reason-code lines and a copy-log button after a failed connection

* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-3
- Add the gui subpackage with the optional GTK 4 / Libadwaita helper

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-2
- Add asynchronous smart-card diagnostics and include readiness in doctor

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-1
- Initial package
