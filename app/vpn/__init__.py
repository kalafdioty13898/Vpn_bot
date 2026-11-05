"""VPN panel adapter package. All panel access goes through adapters."""
from app.vpn.base import PanelError, PanelUser, VpnPanelAdapter, get_adapter

__all__ = ["PanelError", "PanelUser", "VpnPanelAdapter", "get_adapter"]
