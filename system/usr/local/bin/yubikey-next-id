#!/bin/bash
prefix="${1:-yubikey}"
n=0
while [[ -L /dev/${prefix}${n} ]]; do (( n++ )); done
echo -n "$n"
