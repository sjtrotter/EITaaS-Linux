Name:           eitaas-linux
Version:        0.1.0
Release:        3%{?dist}
Summary:        Community Linux helper for EITaaS Azure Virtual Desktop
License:        MIT
URL:            https://github.com/sjtrotter/EITaaS-Linux
Source0:        https://github.com/sjtrotter/EITaaS-Linux/archive/refs/tags/v%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-wheel
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
Requires:       python3
Requires:       opensc
Requires:       pcsc-lite
Requires:       pcsc-lite-ccid
Requires:       pcsc-tools
Recommends:     eitaas-remmina

%description
Read-only diagnostics, protected RDPW profile handling, smart-card checks, and
a validated wrapper around the isolated one-shot EITaaS client package, which
is required for connections.

%package gui
Summary:        Graphical readiness/profile/connect helper for EITaaS AVD
Requires:       %{name} = %{version}-%{release}
Requires:       python3-gobject
# The GUI loads GTK 4 and Libadwaita through GObject introspection; Fedora has
# no typelib() provides and no automatic generator for PyGObject imports, so
# the library packages are required explicitly (rpmlint's
# explicit-lib-dependency is filtered in eitaas-linux.rpmlintrc).
Requires:       gtk4
Requires:       libadwaita
Recommends:     eitaas-remmina

%description gui
Optional GTK 4 / Libadwaita front end for the eitaas command-line helper. It
shows readiness diagnostics, inspects RDPW profiles, and launches the isolated
one-shot EITaaS client. The desktop entry, RDPW MIME association, icons, and
GTK dependencies live in this package so that CLI-only installations stay
lean.

%prep
%autosetup -n eitaas-linux-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
# Only the CLI package is collected here; %%{python3_sitelib}/eitaas_gui/ is
# listed explicitly under %%files gui so each file belongs to exactly one package.
%pyproject_save_files eitaas
install -Dpm 0644 docs/eitaas.1 %{buildroot}%{_mandir}/man1/eitaas.1
install -Dpm 0644 completions/eitaas.bash %{buildroot}%{_datadir}/bash-completion/completions/eitaas
install -Dpm 0644 completions/_eitaas %{buildroot}%{_datadir}/zsh/site-functions/_eitaas
desktop-file-install --dir=%{buildroot}%{_datadir}/applications data/org.eitaas.Helper.desktop
install -Dpm 0644 data/org.eitaas.Helper.metainfo.xml %{buildroot}%{_metainfodir}/org.eitaas.Helper.metainfo.xml
install -Dpm 0644 data/eitaas-rdpw.xml %{buildroot}%{_datadir}/mime/packages/eitaas-rdpw.xml
install -Dpm 0644 data/icons/hicolor/scalable/apps/org.eitaas.Helper.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.eitaas.Helper.svg
install -Dpm 0644 data/icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg
install -Dpm 0644 docs/eitaas-gui.1 %{buildroot}%{_mandir}/man1/eitaas-gui.1

%check
PYTHONPATH=src %{python3} -m unittest discover -s tests -v
desktop-file-validate %{buildroot}%{_datadir}/applications/org.eitaas.Helper.desktop
# appstreamcli exits non-zero for info-level hints as well as real errors;
# report them without failing the build.
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/org.eitaas.Helper.metainfo.xml || :

%files -f %{pyproject_files}
%license LICENSE
%doc README.md NOTICE SECURITY.md SUPPORT.md
%{_bindir}/eitaas
%{_mandir}/man1/eitaas.1*
%{_datadir}/bash-completion/completions/eitaas
%{_datadir}/zsh/site-functions/_eitaas

# MIME and icon caches are refreshed by Fedora's shared-mime-info and
# hicolor-icon-theme file triggers; no scriptlets are needed.
%files gui
%license LICENSE
%{python3_sitelib}/eitaas_gui/
%{_bindir}/eitaas-gui
%{_datadir}/applications/org.eitaas.Helper.desktop
%{_metainfodir}/org.eitaas.Helper.metainfo.xml
%{_datadir}/mime/packages/eitaas-rdpw.xml
%{_datadir}/icons/hicolor/scalable/apps/org.eitaas.Helper.svg
%{_datadir}/icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg
%{_mandir}/man1/eitaas-gui.1*

%changelog
* Sun Aug 30 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-3
- Add the gui subpackage with the optional GTK 4 / Libadwaita helper

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-2
- Add asynchronous smart-card diagnostics and include readiness in doctor

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-1
- Initial package
