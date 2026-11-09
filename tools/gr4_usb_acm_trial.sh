#!/bin/sh
# Bounded, runtime-only GR IV ACM gadget experiment for a proven Linux shell.
# No firmware or persistent file writes. Default action is preflight only.
# This script has NOT been run on a camera.

set -u

gadget=/sys/kernel/config/usb_gadget/mtp
config=$gadget/configs/c.1
function=$gadget/functions/acm.usb0
link=$config/acm.usb0
udc_file=$gadget/UDC
expected_udc=19c00000.dwc3
trial_seconds=60

fail() {
    printf 'preflight failed: %s\n' "$1" >&2
    exit 1
}

preflight() {
    [ "$(id -u)" = 0 ] || fail 'root in the camera Linux system is required'
    [ -d "$gadget" ] || fail 'stock GR IV MTP gadget is absent'
    [ -r "$gadget/idVendor" ] && [ -r "$gadget/idProduct" ] && [ -r "$gadget/bcdDevice" ] || fail 'USB identity is unreadable'
    identity=$(printf '%s:%s' "$(cat "$gadget/idVendor")" "$(cat "$gadget/idProduct")" | tr 'A-F' 'a-f')
    [ "$identity" = '0x25fb:0x2123' ] || fail "unexpected USB identity: $identity"
    device_revision=$(cat "$gadget/bcdDevice" | tr 'A-F' 'a-f')
    [ "$device_revision" = '0x0111' ] || fail "unexpected USB device revision: $device_revision"
    [ -L "$config/mtp.usb0" ] || fail 'original MTP function link is absent'
    [ ! -e "$function" ] && [ ! -L "$function" ] || fail 'ACM function already exists'
    [ ! -e "$link" ] && [ ! -L "$link" ] || fail 'ACM link already exists'
    [ -r "$udc_file" ] && [ -w "$udc_file" ] || fail 'UDC is not accessible'
    original_udc=$(cat "$udc_file")
    [ "$original_udc" = "$expected_udc" ] || fail "unexpected bound UDC: $original_udc"
    [ -d "/sys/class/udc/$original_udc" ] || fail 'UDC sysfs node is absent'
    [ -r /proc/config.gz ] && command -v zcat >/dev/null 2>&1 || fail 'kernel config is unavailable'
    zcat /proc/config.gz | grep -q '^CONFIG_USB_CONFIGFS_ACM=y$' || fail 'ACM configfs function is disabled'
    [ -r /lib/modules/5.15.190/kernel/drivers/usb/gadget/function/usb_f_acm.ko ] || fail 'ACM module is absent'
    printf 'preflight passed: %s, UDC=%s, MTP link present\n' "$identity" "$original_udc"
}

owned_function=0
owned_link=0
unbound=0

restore() {
    result=$?
    trap - 0 1 2 15
    [ "$unbound" = 1 ] || exit "$result"
    current_udc=$(cat "$udc_file" 2>/dev/null) || current_udc=unreadable
    if [ "$current_udc" != "$original_udc" ] && [ -n "$current_udc" ]; then
        printf 'restore incomplete: UDC changed externally to %s\n' "$current_udc" >&2
        exit 1
    fi
    if [ -n "$current_udc" ]; then
        printf '\n' > "$udc_file" || { printf 'restore failed: cannot unbind UDC\n' >&2; exit 1; }
    fi
    if [ "$owned_link" = 1 ]; then
        rm "$link" || { printf 'restore failed: cannot remove ACM link\n' >&2; exit 1; }
    fi
    if [ "$owned_function" = 1 ]; then
        rmdir "$function" || { printf 'restore failed: cannot remove ACM function\n' >&2; exit 1; }
    fi
    printf '%s\n' "$original_udc" > "$udc_file" || {
        printf 'restore failed: cannot rebind original MTP gadget\n' >&2
        exit 1
    }
    printf 'original MTP gadget rebound; ACM trial removed\n'
    exit "$result"
}

case "${1:-}" in
    ''|--preflight)
        preflight
        ;;
    --trial)
        preflight
        trap restore 0
        trap 'exit 130' 1 2 15
        printf '\n' > "$udc_file" || fail 'cannot unbind original gadget'
        unbound=1
        mkdir "$function" || fail 'cannot create ACM function'
        owned_function=1
        ln -s functions/acm.usb0 "$config/" || fail 'cannot attach ACM to MTP configuration'
        owned_link=1
        printf '%s\n' "$original_udc" > "$udc_file" || fail 'cannot bind composite gadget'
        printf 'ACM trial active for %s seconds; USB will disconnect and re-enumerate\n' "$trial_seconds"
        sleep "$trial_seconds"
        ;;
    *)
        printf 'usage: sh %s [--preflight|--trial]\n' "$0" >&2
        exit 2
        ;;
esac
