from iconservice import *


class PromoDB:
  _NAME = 'PromoDBDB'
  _PROMO_SWITCH = 'PROMO_SWITCH'
  _PROMO_JACKPOT = 'PROMO_JACKPOT'
  _PROMO_JACKPOT_WINS = 'PROMO_JACKPOT_WINS'

  def __init__(self, db: IconScoreDatabase):
    name = PromoDB._NAME
    # holds the current promo ON/OFF value
    self._promo_switch = VarDB(f'{name}_{self._PROMO_SWITCH}', db, value_type=bool)
    # holds the current value of the jackpot
    self._promo_jackpot = VarDB(f'{name}_{self._PROMO_JACKPOT}', db, value_type=int)
    # holds how many jackpots have been won (max 4)
    self._promo_jackpot_wins = VarDB(f'{name}_{self._PROMO_JACKPOT_WINS}', db, value_type=int)

  @property
  def promo_switch(self):
    return self._promo_switch

  @property
  def promo_jackpot(self):
    return self._promo_jackpot

  @property
  def promo_jackpot_wins(self):
    return self._promo_jackpot_wins
