from iconservice import *


class Utils:

  def __init__(self):
    pass

  @staticmethod
  def enum_names(cls):
    return [i for i in cls.__dict__.keys() if i[:1] != '_']
