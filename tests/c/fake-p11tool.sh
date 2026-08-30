#!/bin/sh
# Fake p11tool for tests/c/test_pkcs11_discovery.c. Mirrors real behaviour:
# "--list-certs --only-urls TOKEN" prints nothing and exits 1 when the token
# holds no certificate ("No matching objects found" goes to stderr).
# FAKE_P11TOOL_MODE selects the scenario. Labels follow OpenSC's pkcs15-piv.c;
# every value is synthetic.
mode=${FAKE_P11TOOL_MODE:-piv}
trust='pkcs11:model=p11-kit-trust;manufacturer=PKCS%2311%20Kit;serial=1;token=System%20Trust'
empty='pkcs11:model=empty;manufacturer=test;serial=2;token=Empty%20Token'
piv='pkcs11:model=PKCS%2315%20emulated;manufacturer=piv_II;serial=3;token=PIV_II'

case "$1" in
--list-token-urls)
	case "$mode" in
	tokens-fail) echo "error" >&2; exit 1 ;;
	all-empty) printf '%s\n%s\n' "$trust" "$empty"; exit 0 ;;
	*) printf '%s\n%s\n%s\n' "$trust" "$empty" "$piv"; exit 0 ;;
	esac
	;;
--list-certs)
	token=$3
	case "$token" in
	*p11-kit-trust*)
		echo "trust token must not be queried" >&2
		exit 99
		;;
	*Empty*)
		echo "No matching objects found" >&2
		exit 1
		;;
	*)
		if [ "$mode" = signal ]; then
			kill -TERM $$
		fi
		if [ "$mode" = malformed ]; then
			echo "$token;id=%01;object=Certificate%20for%20PIV%20Authentication;type=cert"
			exit 1
		fi
		for pair in '%01 Certificate%20for%20PIV%20Authentication' \
			'%02 Certificate%20for%20Digital%20Signature' \
			'%03 Certificate%20for%20Key%20Management' \
			'%04 Certificate%20for%20Card%20Authentication'; do
			set -- $pair
			echo "$token;id=$1;object=$2;type=cert"
		done
		exit 0
		;;
	esac
	;;
*)
	echo "unexpected arguments: $*" >&2
	exit 64
	;;
esac
