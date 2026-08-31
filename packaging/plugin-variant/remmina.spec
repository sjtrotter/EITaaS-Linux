# Remmina 1.4.43 base for the EITaaS AAD/PIV plugin variant (issue #101, ADR-0003 Track 2).
#
# This is Fedora's own remmina.spec (remmina-1.4.41-2.fc44) with ONLY the source
# bumped to the pinned Remmina 1.4.43 snapshot recorded in
# packaging/remmina/sources.json:
#
#   commit 030946c83fe1b7218a21b6d32f9c975b243b7031  ( = git describe v1.4.43-142-g030946c83 )
#
# Rationale for the pinned snapshot rather than the bare v1.4.43 release tag
# (7be0cf2348d149c6bf5bd882fe91d3bec7d6aebb): the RDP AAD web-authentication
# code the companion remmina-plugin-rdp-piv package extends
# (plugins/rdp/rdp_web_auth.c) does NOT exist at the v1.4.43 tag; it landed on
# master afterwards and is present in this 030946c8 snapshot. Building both the
# base and the plugin from this identical source is what makes them ABI-matched.
# This is a VANILLA build (no EITaaS patches, WITH_RDP_AUTH_AAD off by default) —
# it is the clean base whose remmina-plugins-rdp the -piv package replaces.
#
# The packaging (dependencies, cmake flags, subpackages, %%check) is unchanged
# from Fedora so the base tracks the distribution's own remmina; ONLY the
# source/EVR and this changelog head differ (the historical Fedora changelog
# below is trimmed to the most recent entry).
#
# EVR: snapshot versioning 1.4.43^142.g030946c83-1 -- the "^142.g030946c83"
# marks a post-v1.4.43 snapshot, so it sorts ABOVE both Fedora stock
# (1.4.41-2) and any future real 1.4.43-1, and BELOW 1.4.44. The companion
# remmina-plugin-rdp-piv Requires this exact EVR, so the base and the plugin
# MUST always be built and released together.

%global commit 030946c83fe1b7218a21b6d32f9c975b243b7031

Name: remmina
Version: 1.4.43^142.g030946c83
Release: 1%{?dist}
Summary: Remote Desktop Client
License: GPL-2.0-or-later and MIT
URL: https://remmina.org

# Pinned snapshot archive (sha256 recorded in packaging/remmina/sources.json:
# 8976850314dddab8cfe74f413233a712e7ba4b6ccf72b56cbf635b51f1ea2801)
Source0: https://gitlab.com/Remmina/Remmina/-/archive/%{commit}/Remmina-%{commit}.tar.gz

# Cmake helper file to easy build plugins outside remmina source tree
# See http://www.muflone.com/remmina-plugin-rdesktop/english/install.html which
# use http://www.muflone.com/remmina-plugin-builder/ with remmina bundled source.
# So we can't use it directly only as instructions.
Source1: pluginBuild-CMakeLists.txt

BuildRequires: cmake >= 3.2
BuildRequires: cups-devel
BuildRequires: desktop-file-utils
BuildRequires: gcc-c++
BuildRequires: gettext
BuildRequires: harfbuzz-devel
BuildRequires: intltool
%if 0%{?rhel} < 10
# Upstream doesn't support KF6 yet https://gitlab.com/Remmina/Remmina/-/issues/3141
BuildRequires: kf5-kwallet-devel
%endif
BuildRequires: libappstream-glib
BuildRequires: libgcrypt-devel
BuildRequires: libsodium-devel
BuildRequires: python3-devel
BuildRequires: xdg-utils
BuildRequires: pkgconfig(appindicator3-0.1)
%if 0%{?fedora} || 0%{?rhel} == 8
BuildRequires: pkgconfig(avahi-ui)
BuildRequires: pkgconfig(avahi-ui-gtk3)
%endif
BuildRequires: pkgconfig(freerdp3) >= 3.3.0
BuildRequires: freerdp
BuildRequires: pkgconfig(gtk+-3.0)
BuildRequires: pkgconfig(json-glib-1.0)
BuildRequires: pkgconfig(libsecret-1)
%if 0%{?fedora} >= 37 || 0%{?rhel} >= 10
BuildRequires: pkgconfig(libsoup-3.0)
%else
BuildRequires: pkgconfig(libsoup-2.4)
%endif
BuildRequires: pkgconfig(libssh) >= 0.8.0
BuildRequires: pkgconfig(libvncserver)
BuildRequires: pkgconfig(libpcre2-8)
%if 0%{?fedora} || 0%{?rhel} == 8
BuildRequires: pkgconfig(spice-client-gtk-3.0)
%endif
BuildRequires: pkgconfig(vte-2.91)

%if 0%{?fedora} >= 37 || 0%{?rhel} >= 10
BuildRequires: pkgconfig(webkit2gtk-4.1)
%else
BuildRequires: pkgconfig(webkit2gtk-4.0)
%endif

BuildRequires: pkgconfig(x11)
BuildRequires: pkgconfig(xkbfile)
BuildRequires: pkgconfig(libcurl)
BuildRequires: pkgconfig(fuse3)

# We don't ship these remmina plugins any longer.
Obsoletes: %{name}-plugins-nx < %{version}-%{release}
Obsoletes: %{name}-plugins-st < %{version}-%{release}
Obsoletes: %{name}-plugins-xdmcp < %{version}-%{release}

Recommends: %{name}-plugins-exec
Recommends: %{name}-plugins-rdp
Recommends: %{name}-plugins-secret
Recommends: %{name}-plugins-vnc

%if 0%{?fedora}
Recommends: openh264
%endif

%description
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

Remmina supports multiple network protocols in an integrated and consistent
user interface. Currently RDP, VNC and SSH are supported.

Please don't forget to install the plugins for the protocols you want to use.

%package devel
Summary: Development files for %{name}
Requires: %{name} = %{version}-%{release}
Requires: pkgconfig

%description devel
The %{name}-devel package contains header files for developing plugins for
%{name}.

%package plugins-exec
Summary: External execution plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-exec
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the plugin to execute external processes (commands or
applications) from the Remmina window.

%package plugins-secret
Summary: Keyring integration for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}
Obsoletes: %{name}-plugins-gnome < %{version}-%{release}
Provides: %{name}-plugins-gnome%{?_isa} = %{version}-%{release}

%description plugins-secret
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the plugin with keyring support for the Remmina remote
desktop client.

%package plugins-rdp
Summary: RDP plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-rdp
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the Remote Desktop Protocol (RDP) plugin for the Remmina
remote desktop client.

%package plugins-vnc
Summary: VNC plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-vnc
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the VNC plugin for the Remmina remote desktop
client.

%if 0%{?fedora} || 0%{?rhel} == 8
%package plugins-spice
Summary: SPICE plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-spice
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the SPICE plugin for the Remmina remote desktop
client.
%endif

%package plugins-www
Summary: WWW plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-www
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the WWW plugin (web browser with authentication) for the
Remmina remote desktop client.

%if 0%{?rhel} < 10
%package plugins-kwallet
Summary: KDE Wallet plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-kwallet
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the KDE Wallet plugin for the Remmina remote desktop
client. It will be activated automatically if KDE Wallet is installed and
running.
%endif

%if 0%{?fedora} || 0%{?rhel} == 8
%package plugins-x2go
Summary: x2go plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}
Requires: pyhoca-cli

%description plugins-x2go
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the x2go plugin for the Remmina remote desktop client.
%endif

%package plugins-python
Summary: Python plugin for Remmina Remote Desktop Client
Requires: %{name}%{?_isa} = %{version}-%{release}

%description plugins-python
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains the python plugin for the Remmina remote desktop client.

%package gnome-session
Summary: Gnome Shell session for Remmina kiosk mode
Requires: %{name}%{?_isa} = %{version}-%{release}
Requires: gnome-session

%description gnome-session
Remmina is a remote desktop client written in GTK+, aiming to be useful for
system administrators and travelers, who need to work with lots of remote
computers in front of either large monitors or tiny net-books.

This package contains Remmina kiosk mode, including a Gnome Shell session
that shows up under the display manager session menu.

%prep
%autosetup -p1 -n Remmina-%{commit}

%build
%cmake \
    -DCMAKE_INSTALL_LIBDIR=%{_lib} \
    -DCMAKE_INSTALL_PREFIX=%{_prefix} \
    -DHAVE_LIBAPPINDICATOR=ON \
%if 0%{?fedora} || 0%{?rhel} == 8
    -DWITH_AVAHI=ON \
%else
    -DWITH_AVAHI=OFF \
%endif
    -DWITH_FREERDP3=ON \
    -DWITH_GCRYPT=ON \
    -DWITH_GETTEXT=ON \
%if 0%{?rhel} < 10
    -DWITH_KF5WALLET=ON \
%else
    -DWITH_KF5WALLET=OFF \
%endif
    -DWITH_KIOSK_SESSION=ON \
    -DWITH_LIBSSH=ON \
    -DWITH_NEWS=OFF \
    -DWITH_PYTHONLIBS=ON \
%if 0%{?fedora} || 0%{?rhel} == 8
    -DWITH_SPICE=ON \
%else
    -DWITH_SPICE=OFF \
%endif
    -DWITH_VTE=ON \
%if 0%{?fedora} || 0%{?rhel} == 8
    -DWITH_X2GO=ON
%else
    -DWITH_X2GO=OFF
%endif
%cmake_build

%install
%cmake_install

mkdir -p %{buildroot}/%{_libdir}/cmake/%{name}/
cp -pr cmake/*.cmake %{buildroot}/%{_libdir}/cmake/%{name}/
cp -pr config.h.in %{buildroot}/%{_includedir}/%{name}/
cp -p %{SOURCE1} %{buildroot}/%{_includedir}/%{name}/

%find_lang %{name}

%check
desktop-file-validate %{buildroot}/%{_datadir}/applications/*.desktop
appstream-util validate-relax --nonet %{buildroot}/%{_datadir}/metainfo/*.appdata.xml

%files -f %{name}.lang
%license LICENSE
%doc AUTHORS CHANGELOG.md README.md
%{_bindir}/%{name}
%{_bindir}/%{name}-file-wrapper
%{_datadir}/metainfo/*.appdata.xml
%{_datadir}/applications/*.desktop
%{_datadir}/icons/hicolor/*/actions/*.*
%{_datadir}/icons/hicolor/*/apps/*.*
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-*.svg
%{_datadir}/icons/hicolor/*/status/org.remmina.Remmina-status.svg
%{_datadir}/icons/hicolor/apps/*.svg
%{_datadir}/mime/packages/*.xml
%{_datadir}/%{name}/
%dir %{_libdir}/remmina/
%dir %{_libdir}/remmina/plugins/
%{_mandir}/man1/%{name}.*
%{_mandir}/man1/%{name}-file-wrapper.*

%files devel
%{_includedir}/%{name}/
%{_libdir}/pkgconfig/%{name}.pc
%{_libdir}/cmake/%{name}/*.cmake

%files plugins-exec
%{_libdir}/remmina/plugins/remmina-plugin-exec.so

%files plugins-secret
%{_libdir}/remmina/plugins/remmina-plugin-secret.so

%files plugins-rdp
%{_libdir}/remmina/plugins/remmina-plugin-rdp.so
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-rdp-ssh-symbolic.svg
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-rdp-symbolic.svg

%files plugins-vnc
%{_libdir}/remmina/plugins/remmina-plugin-vnc.so
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-vnc-ssh-symbolic.svg
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-vnc-symbolic.svg

%if 0%{?fedora} || 0%{?rhel} == 8
%files plugins-spice
%{_libdir}/remmina/plugins/remmina-plugin-spice.so
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-spice-ssh-symbolic.svg
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-spice-symbolic.svg
%endif

%files plugins-www
%{_libdir}/remmina/plugins/remmina-plugin-www.so

%if 0%{?rhel} < 10
%files plugins-kwallet
%{_libdir}/remmina/plugins/remmina-plugin-kwallet.so
%endif

%files plugins-python
%{_libdir}/remmina/plugins/remmina-plugin-python_wrapper.so

%if 0%{?fedora} || 0%{?rhel} == 8
%files plugins-x2go
%{_libdir}/remmina/plugins/remmina-plugin-x2go.so
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-x2go-ssh-symbolic.svg
%{_datadir}/icons/hicolor/*/emblems/org.remmina.Remmina-x2go-symbolic.svg
%endif

%files gnome-session
%{_bindir}/gnome-session-remmina
%{_bindir}/remmina-gnome
%{_datadir}/gnome-session/sessions/remmina-gnome.session
%{_datadir}/xsessions/remmina-gnome.desktop
%{_mandir}/man1/gnome-session-remmina.1*
%{_mandir}/man1/remmina-gnome.1*

%changelog
* Mon Aug 31 2026 EITaaS-Linux <noreply@example.invalid> - 1.4.43^142.g030946c83-1
- EITaaS COPR variant base (issue #101, ADR-0003 Track 2).
- Bump to the pinned Remmina 1.4.43 snapshot 030946c8 (git describe
  v1.4.43-142-g030946c83) recorded in packaging/remmina/sources.json; the RDP
  AAD web-auth code the remmina-plugin-rdp-piv package extends is present in
  this snapshot but not in the bare v1.4.43 release tag.
- Vanilla build (no EITaaS patches); packaging unchanged from Fedora's
  remmina-1.4.41-2.fc44.

* Sat Jan 17 2026 Fedora Release Engineering <releng@fedoraproject.org> - 1.4.41-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_44_Mass_Rebuild
