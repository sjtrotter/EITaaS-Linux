_eitaas()
{
    local current previous commands
    COMPREPLY=()
    current="${COMP_WORDS[COMP_CWORD]}"
    previous="${COMP_WORDS[COMP_CWORD-1]}"
    commands="doctor inspect-profile smartcard connect certificates"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$current") )
        return
    fi
    case "${COMP_WORDS[1]}" in
        doctor) COMPREPLY=( $(compgen -W "--json" -- "$current") ) ;;
        connect) COMPREPLY=( $(compgen -f -- "$current") ) ;;
        smartcard) COMPREPLY=( $(compgen -W "status" -- "$current") ) ;;
        certificates) COMPREPLY=( $(compgen -W "fetch inspect" -- "$current") ) ;;
        inspect-profile)
            if [ "$previous" = "inspect-profile" ]; then
                COMPREPLY=( $(compgen -f -- "$current") )
            else
                COMPREPLY=( $(compgen -W "--json" -- "$current") )
            fi
            ;;
    esac
}
complete -F _eitaas eitaas
