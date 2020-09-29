from iconservice import *
from ..scorelib.utils import Utils


class GameMode:
  EASY = 0
  MEDIUM = 1
  HARD = 2
  JACKPOT = 3


class GameModel:

  def __init__(self, game_id: int, player_address: Address, bet_amount: int, active_game_num: int,
               game_start_datetime: int, game_mode: int, max_level_allowed=0, balance=0, level=0):
    self._game_id = game_id
    self._player_address = player_address
    self._level = level
    self._bet_amount = bet_amount
    self._active_game_num = active_game_num
    self._balance = balance
    self._game_started_datetime = game_start_datetime
    self._max_level_allowed = max_level_allowed
    self._game_mode = game_mode
    self._bombs = ""
    self._selected_tiles = ""

  def __str__(self):
    response = {
      'game_id': self._game_id,
      'player_address': f"{self._player_address}",
      'level': self._level,
      'max_level_allowed': self._max_level_allowed,
      'bet_amount': self._bet_amount,
      'balance': self._balance,
      'active_game_num': self._active_game_num,
      'game_mode': self._game_mode,
      'game_started_datetime': self._game_started_datetime,
      'bombs': self._bombs,
      'selected_tiles': self._selected_tiles
    }
    return json_dumps(response)
