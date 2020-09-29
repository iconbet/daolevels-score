from ..scorelib.id_factory import *
from ..scorelib.utils import *
from iconservice import *
from .game_model import *
from ..game.consts import *


# ================================================
# Interface to the game repository
# ================================================

class GameNotFoundException(Exception):
  pass


class MaxConcurrentGamesReached(Exception):
  pass


class IGameRepository(IdFactory):
  # ================================================
  # Interface to the game repository
  # ================================================
  _NAME = 'IGameRepository'

  def __init__(self, db: IconScoreDatabase):
    name = IGameRepository._NAME
    super().__init__(name, db)
    self._db = db

  def get(self, player_address, active_game_num: int) -> str:
    game_repository = GameDB(player_address, self._db)
    return game_repository.active_games[str(active_game_num)]

  def create(self, player_address: Address, bet_amount: int, datetime: int, game_mode: int, max_level: int) -> str:
    active_game_num = 0
    game_id = self.get_uid()
    game_repository = GameDB(player_address, self._db)
    active_games = game_repository.active_games
    num_games_open = game_repository.number_of_open_games.get()
    if num_games_open == MAX_OPEN_GAMES:
      raise MaxConcurrentGamesReached(f"No more than 4 concurrent games can be played at once")

    num_games_open = num_games_open + 1
    for i in range(1, 5):
      if str(i) not in active_games:
        active_game_num = i
        break

    model = GameModel(game_id, player_address, bet_amount, active_game_num, datetime, max_level, game_mode)
    active_games[str(active_game_num)] = str(model)
    game_repository.number_of_open_games.set(num_games_open)

    return active_games[str(active_game_num)]

  def increase_level_and_balance(self, player_address: Address, active_game_num: int, random_number: int, square_id: int) -> None:
    game_db = GameDB(player_address, self._db)
    active_games = game_db.active_games
    json_object = json_loads(active_games[str(active_game_num)])
    new_level = int(json_object["level"]) + 1
    balance = int(json_object["bet_amount"])
    game_mode = json_object["game_mode"]
    bomb = str(json_object["bombs"])
    selected_tiles = str(json_object["selected_tiles"])

    # check if bomb string is empty
    if not bomb:
      json_object["selected_tiles"] = str(square_id)
      if game_mode != GameMode.HARD:
        json_object["bombs"] = str(random_number)
      else:
        if random_number == 1:
          json_object["bombs"] = "2:3"
        elif random_number == 2:
          json_object["bombs"] = "1:3"
        elif random_number == 3:
          json_object["bombs"] = "1:2"
    else:
      json_object["selected_tiles"] = selected_tiles + "," + str(square_id)
      if game_mode != GameMode.HARD:
        json_object["bombs"] = bomb + "," + str(random_number)
      else:
        if random_number == 1:
          json_object["bombs"] = bomb + "," + "2:3"
        elif random_number == 2:
          json_object["bombs"] = bomb + "," + "1:3"
        elif random_number == 3:
          json_object["bombs"] = bomb + "," + "1:2"

    new_balance = 0
    if game_mode == GameMode.EASY:
      new_balance = (balance * float(ROW_MULTIPLIER[new_level]))
    elif game_mode == GameMode.MEDIUM:
      new_balance = (balance * float(MEDIUM_ROW_MULTIPLIER[new_level]))
    elif game_mode == GameMode.HARD:
      new_balance = (balance * float(HARD_ROW_MULTIPLIER[new_level]))

    Logger.info(f"New balance is: {new_balance}", "BALANCE")
    Logger.info(f"New LEVEL is: {new_level}", "LEVEL")
    json_object["level"] = new_level
    json_object["balance"] = int(new_balance)
    game_db.active_games[str(active_game_num)] = json_dumps(json_object)

  def increase_level(self, player_address: Address, active_game_num: int, random_number: int, square_id: int):
    game_db = GameDB(player_address, self._db)
    active_games = game_db.active_games
    json_object = json_loads(active_games[str(active_game_num)])
    bomb = str(json_object["bombs"])
    selected_tiles = str(json_object["selected_tiles"])
    new_level = int(json_object["level"]) + 1

    # check if bomb string is empty
    if not bomb:
      json_object["selected_tiles"] = str(square_id)
      if new_level < 5:
        json_object["bombs"] = str(random_number)
      else:
        if random_number == 1:
          json_object["bombs"] = "2:3:4"
        elif random_number == 2:
          json_object["bombs"] = "1:3:4"
        elif random_number == 3:
          json_object["bombs"] = "1:2:4"
        elif random_number == 4:
          json_object["bombs"] = "1:2:3"
    else:
      json_object["selected_tiles"] = selected_tiles + "," + str(square_id)
      if new_level < 5:
        json_object["bombs"] = bomb + "," + str(random_number)
      else:
        if random_number == 1:
          json_object["bombs"] = bomb + "," + "2:3:4"
        elif random_number == 2:
          json_object["bombs"] = bomb + "," + "1:3:4"
        elif random_number == 3:
          json_object["bombs"] = bomb + "," + "1:2:4"
        elif random_number == 4:
          json_object["bombs"] = bomb + "," + "1:2:3"

    json_object["level"] = new_level
    game_db.active_games[str(active_game_num)] = json_dumps(json_object)

  def get_open_games(self, player_address: Address) -> list:
    game_db = GameDB(player_address, self._db)
    active_games = game_db.active_games
    active_games_list = list()

    for i in range(1, 5):
      if str(i) in active_games:
        active_games_list.append(json_loads(active_games[str(i)]))

    return active_games_list

  def get_finished_game_list(self, player_address: Address) -> str:
    game_db = GameDB(player_address, self._db)
    finished_game_ids = game_db.finish_game_ids.get()
    return finished_game_ids

  def remove_from_active_game(self, player_address: Address, active_game_num: int) -> int:
    game_db = GameDB(player_address, self._db)
    active_games = game_db.active_games
    json_object = json_loads(active_games[str(active_game_num)])
    game_id = json_object["game_id"]

    # add a new game_id to the concat string
    finished_game_ids = game_db.finish_game_ids.get()
    finished_games_append = str(game_id) + "," + str(finished_game_ids)
    game_db.finish_game_ids.set(finished_games_append)

    # add game details to the finished games record
    game_db.finished_game_records[str(game_id)] = json_dumps(json_object)

    # reduce active games by 1
    game_db.number_of_open_games.set(game_db.number_of_open_games.get() - 1)

    # lastly remove the game for from the active list
    active_games.remove(str(active_game_num))
    return game_id

  # ================================================
  # Checks
  # ================================================
  def game_exists(self, game_id: int, player_address: Address) -> None:
    game_repository = GameDB(player_address, self._db)
    if game_id not in game_repository.active_games:
      raise GameNotFoundException(f'Game does not exist: Game id provided: {game_id}')


class GameDB(object):
  _NAME = 'GameDB'
  _ACTIVE_GAMES_DICT = 'active_games'
  _FINISHED_GAME_DICT = 'finished_games'
  _NUMBER_OF_GAMES = 'number_of_open_games'

  def __init__(self, player_address: Address, db: IconScoreDatabase):
    name = GameDB._NAME
    # Holds the game objects of all current games player has in progress
    self._active_games = DictDB(f'{name}_{self._ACTIVE_GAMES_DICT}_{player_address}', db, value_type=str, depth=1)
    # Holds a record of all games player has finished
    # [0] = holds all game object wih game_id as the key
    # [1] = holds a comma delimited string of all game ids history as the key
    # open._finished_game_records[1232] =
    #   {
    #    "game_id": "0x759c",
    #    "player_address": "hxe7af5fcfd8dfc67530a01a0e403882687528dfcb",
    #    "status": "NOT_STARTED",
    #    "level": "0x0",
    #    "bet_amount": "0xa"
    #   },
    self._finished_game_records = DictDB(f'{name}_{self._FINISHED_GAME_DICT}_{player_address}', db, value_type=str)
    # open._finished_game_ids[history] = "1121, 1212, 1212, 1212, 1212, 1212, 1212, 1221"
    self._finished_game_ids = VarDB(f'{name}_{self._FINISHED_GAME_DICT}_{player_address}', db, value_type=str)
    # Holds a record of the running total of concurrent games currently open
    self._number_of_games = VarDB(f'{name}_{self._NUMBER_OF_GAMES}_{player_address}', db, value_type=int)

  @property
  def active_games(self):
    return self._active_games

  @property
  def finished_game_records(self):
    return self._finished_game_records

  @property
  def finish_game_ids(self):
    return self._finished_game_ids

  @property
  def number_of_open_games(self):
    return self._number_of_games
