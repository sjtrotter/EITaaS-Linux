# Contributing

Contributions are welcome. Keep changes narrowly scoped and add tests for new
behavior. Run the test suite before opening a pull request.

Never commit real `.rdp` or `.rdpw` files, authentication callbacks, certificate
or private-key material, packet captures, smart-card data, tenant identifiers, or
agent-local state. Tests must use the explicitly synthetic fixture under
`tests/fixtures/`.

Security reports belong in the private channel described in `SECURITY.md`, not
in public issues.
