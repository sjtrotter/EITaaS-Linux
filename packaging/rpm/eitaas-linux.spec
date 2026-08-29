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
Requires:       python3
Requires:       freerdp
Requires:       opensc
Requires:       pcsc-lite
Requires:       pcsc-lite-ccid
Requires:       pcsc-tools

%description
Read-only diagnostics, protected RDPW profile handling, smart-card checks, and
safe FreeRDP client selection. A FreeRDP 3 build with AAD and PC/SC support is
required for connections.

%prep
%autosetup -n eitaas-linux-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files eitaas
install -Dpm 0644 docs/eitaas.1 %{buildroot}%{_mandir}/man1/eitaas.1
install -Dpm 0644 completions/eitaas.bash %{buildroot}%{_datadir}/bash-completion/completions/eitaas
install -Dpm 0644 completions/_eitaas %{buildroot}%{_datadir}/zsh/site-functions/_eitaas

%check
PYTHONPATH=src %{python3} -m unittest discover -s tests -v

%files -f %{pyproject_files}
%license LICENSE
%doc README.md NOTICE SECURITY.md SUPPORT.md
%{_bindir}/eitaas
%{_mandir}/man1/eitaas.1*
%{_datadir}/bash-completion/completions/eitaas
%{_datadir}/zsh/site-functions/_eitaas

%changelog
* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-3
- Add a resizable single-monitor connection mode

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-2
- Add asynchronous smart-card diagnostics and include readiness in doctor

* Sat Aug 29 2026 EITaaS-Linux contributors <noreply@example.invalid> - 0.1.0-1
- Initial package
