# coding=utf-8

from . import constant
from resource import resource
from .screenshot import Screenshot


def makeScreenShot(flag: int = 255):
    window = Screenshot(flag)
    return window


__all__ = ["constant", "Screenshot", "makeScreenShot"]
