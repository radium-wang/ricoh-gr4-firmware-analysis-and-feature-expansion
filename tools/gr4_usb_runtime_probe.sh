#!/bin/sh
# Read-only GR IV Linux USB gadget probe. Run inside the camera's Linux shell.
# Output goes to stdout; redirect it to a file on the SD card if desired.

set -u

line() {
    printf '\n== %s ==\n' "$1"
}

show_file() {
    if [ -r "$1" ]; then
        printf '%s: ' "$1"
        cat "$1"
        printf '\n'
    else
        printf '%s: unavailable\n' "$1"
    fi
}

line 'identity'
uname -a
id

line 'gadget root'
gadget=/sys/kernel/config/usb_gadget/mtp
if [ ! -d "$gadget" ]; then
    printf 'GR IV mtp gadget is absent\n'
    exit 0
fi
show_file "$gadget/idVendor"
show_file "$gadget/idProduct"
show_file "$gadget/bcdDevice"
show_file "$gadget/UDC"

line 'USB device controllers'
for item in /sys/class/udc/*; do
    [ -e "$item" ] && printf '%s\n' "${item##*/}"
done

line 'functions and configurations'
for item in "$gadget"/functions/* "$gadget"/configs/*; do
    [ -e "$item" ] && printf '%s\n' "${item#"$gadget"/}"
done
for item in "$gadget"/configs/*/*; do
    [ -L "$item" ] && printf '%s -> %s\n' "${item#"$gadget"/}" "$(readlink "$item")"
done

line 'kernel config for USB gadget functions'
if [ -r /proc/config.gz ] && command -v zcat >/dev/null 2>&1; then
    zcat /proc/config.gz | grep -E '^(CONFIG_USB_(CONFIGFS|F_|G_SERIAL|LIBCOMPOSITE|DWC3)|# CONFIG_USB_(CONFIGFS|F_|G_SERIAL|LIBCOMPOSITE|DWC3))' || true
else
    printf '/proc/config.gz or zcat unavailable\n'
fi

line 'gadget-related loaded modules'
if [ -r /proc/modules ]; then
    grep -E '^(libcomposite|usb_f_|u_serial|u_ether|dwc3|configfs) ' /proc/modules || true
fi

line 'candidate device-side serial nodes'
for item in /dev/ttyGS*; do
    [ -e "$item" ] && printf '%s\n' "$item"
done
