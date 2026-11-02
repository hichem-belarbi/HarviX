"""
models/device.py — Entités de base : Device, Slot, Output
"""
from __future__ import annotations
from typing import Optional


class Device:
    def __init__(self, uid: int, model: str, quantity: str,
                 i2c_address: Optional[str] = None, params: Optional[dict] = None):
        self.uid         = uid
        self.model       = model
        self.quantity    = quantity
        self.i2c_address = i2c_address
        self.params      = params or {}

    def display_name(self) -> str:
        addr = f" @{self.i2c_address}" if self.i2c_address else ""
        return f"{self.model}{addr} ({self.quantity})"

    def short_name(self) -> str:
        return self.model

    def to_dict(self) -> dict:
        d: dict = {"uid": self.uid, "model": self.model, "quantity": self.quantity}
        if self.i2c_address:
            d["i2c_address"] = self.i2c_address
        if self.params:
            d["params"] = self.params
        return d

    @staticmethod
    def from_dict(data: dict) -> "Device":
        return Device(data["uid"], data["model"], data["quantity"],
                      data.get("i2c_address"), data.get("params", {}))

    def __repr__(self):
        return f"<Device uid={self.uid} {self.model} {self.quantity}>"


class Slot:
    def __init__(self, slot_id: int, bus_type: str, bus: str,
                 label: str, max_devices: int = 1):
        self.slot_id     = slot_id
        self.bus_type    = bus_type
        self.bus         = bus
        self.label       = label
        self.max_devices = max_devices
        self.devices: list[Device] = []

    def can_add(self) -> bool:
        return len(self.devices) < self.max_devices

    def is_empty(self) -> bool:
        return not self.devices

    def is_full(self) -> bool:
        return len(self.devices) >= self.max_devices

    def add_device(self, device: Device) -> bool:
        if not self.can_add():
            return False
        if self.bus_type == "I2C" and device.i2c_address:
            if device.i2c_address in {d.i2c_address for d in self.devices}:
                return False
        self.devices.append(device)
        return True

    def remove_device(self, uid: int) -> bool:
        before = len(self.devices)
        self.devices = [d for d in self.devices if d.uid != uid]
        return len(self.devices) < before

    def used_addresses(self) -> list[str]:
        return [d.i2c_address for d in self.devices if d.i2c_address]

    def clear(self):
        self.devices.clear()

    def __repr__(self):
        return f"<Slot {self.slot_id} {self.bus_type} {len(self.devices)}/{self.max_devices}>"


class Output:
    def __init__(self, output_id: int, out_type: str, label: str):
        self.output_id = output_id
        self.type      = out_type
        self.label     = label
        self.active    = False

    def toggle(self):
        self.active = not self.active

    def __repr__(self):
        return f"<Output {self.output_id} {self.type} active={self.active}>"
