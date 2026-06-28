import pytest
import sys
import os

# Ensure we can import main from app folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import validate_ip_cidr

def test_validate_ipv4_and_networks():
    assert validate_ip_cidr("1.2.3.4") is True
    assert validate_ip_cidr("192.168.1.0/24") is True
    assert validate_ip_cidr("anywhere") is True
    assert validate_ip_cidr("all") is True

def test_validate_ipv6_and_networks():
    assert validate_ip_cidr("2a06:9801:1e::184") is True
    assert validate_ip_cidr("2001:db8::/32") is True
    assert validate_ip_cidr("::1") is True

def test_validate_invalid_inputs():
    assert validate_ip_cidr("1.2.3.256") is False
    assert validate_ip_cidr("google.com") is False
    assert validate_ip_cidr("2001:db8::g") is False
    assert validate_ip_cidr("") is False
