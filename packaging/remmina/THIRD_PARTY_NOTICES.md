# EITaaS Remmina prototype: licenses and sources

The `eitaas-remmina` RPM is a composite distribution. Each component retains
its own license; the RPM `License` expression describes the set of licenses in
the package.

| Component | Packaged source | License | Installed text |
| --- | --- | --- | --- |
| Remmina 1.4.43 (`030946c83fe1b7218a21b6d32f9c975b243b7031`) | `Remmina-030946c83fe1b7218a21b6d32f9c975b243b7031.tar.gz` plus `0001`–`0004` patches | GPL-2.0-or-later, with Remmina's OpenSSL exception | `Remmina-COPYING`, `Remmina-LICENSE`, `Remmina-LICENSE.OpenSSL` |
| EITaaS CAC integration compiled into Remmina | `eitaas_cac_auth.c`, `eitaas_cac_auth.h` | GPL-2.0-or-later | `Remmina-COPYING` |
| FreeRDP 3.30.0 | `3.30.0.tar.gz` | Apache-2.0 | `FreeRDP-LICENSE` |
| CPU-features code distributed in the FreeRDP source | within `3.30.0.tar.gz` | see upstream notice | `FreeRDP-cpufeatures-NOTICE` |
| EITaaS one-shot launcher | `eitaas-remmina` | MIT | `EITaaS-LICENSE` |

The source RPM also contains this manifest, the RPM spec, and every input named
above. The source archive filenames are those recorded by the spec; RPM tools
may display a URL basename for `Source0`.

The EITaaS downstream integration and launcher are copyright 2026 Stephen
Trotter. They were developed with AI assistance and reviewed and tested by
the project maintainer. AI tooling is not identified as an author or copyright
holder.

Upstream projects:

- Remmina: <https://gitlab.com/Remmina/Remmina>
- FreeRDP: <https://github.com/FreeRDP/FreeRDP>
- EITaaS-Linux: <https://github.com/sjtrotter/EITaaS-Linux>
