from iconservice import *
from .scorelib.id_factory import *
from .repository.game_repository import *
from .repository.game_model import *
from .repository.icon_bet_repository import *
from .repository.promo_repository import *
from .repository.game_model import GameMode
from .scorelib.utils import Utils

TAG = 'DAOLevels'


# ================================================
# An interface to roulette score
# ================================================
class RouletteInterface(InterfaceScore):
  @interface
  def get_treasury_min(self) -> int:
    pass

  @interface
  def take_wager(self, _amount: int) -> None:
    pass

  @interface
  def wager_payout(self, _payout: int) -> None:
    pass

  @interface
  def take_rake(self, _amount: int, _payout: int) -> None:
    pass


# ================================================
#  Exceptions
# ================================================
class InvalidGameException(Exception):
  pass


class InvalidPlayerAddress(Exception):
  pass


class InvalidLevelToCashOut(Exception):
  pass


class InvalidBetValue(Exception):
  pass


class InvalidGameMode(Exception):
  pass


class InvalidTileSelection(Exception):
  pass


class InvalidCustomTileRange(Exception):
  pass


class DAOlevels(IconScoreBase):
  _NAME = "DAOlevels"
  _ADMIN_ADDRESS = "Admin_Address"

  # ================================================
  #  Event Logs
  # ================================================
  @eventlog(indexed=1)
  def NewGameStarted(self, game_details: str) -> None:
    pass

  @eventlog(indexed=2)
  def SelectedSquareResult(self, bomb_placed_on: int, result: str) -> None:
    pass

  @eventlog
  def ShowException(self, exception: str):
    pass

  @eventlog(indexed=2)
  def BetSource(self, _from: Address, timestamp: int):
    pass

  @eventlog(indexed=2)
  def FundTransfer(self, recipient: Address, amount: int, note: str):
    pass

  @eventlog(indexed=2)
  def AddToPromoJackpot(self, recipient: Address, amount: int):
    pass

  @eventlog()
  def GenericMessage(self, message: str):
    pass

  def __init__(self, db: IconScoreDatabase) -> None:
    self._name = DAOlevels._NAME
    self._iconBetDB = IconBetDB(db)
    self._promoDB = PromoDB(db)
    self._roulette_score = self.create_interface_score(self._iconBetDB.iconbet_score.get(), RouletteInterface)
    self._game_admin = VarDB(self._ADMIN_ADDRESS, db, value_type=Address)
    self._db = db

    super().__init__(db)

  def on_install(self) -> None:
    super().on_install()
    self._promoDB.promo_switch.set(False)

  def on_update(self) -> None:
    super().on_update()
    
  @external(readonly=True)
  def name(self) -> str:
    return self._name
  
  # ================================================
  #  Internal methods
  # ================================================
  def _create_new_game(self, player_address: Address, bet_amount: int, datetime: int, game_mode: int):
    if bet_amount < BET_MIN:
      raise InvalidBetValue(f'Invalid Min Bet: Min allowed is {BET_MIN}')

    if game_mode not in [GameMode.EASY,
                         GameMode.MEDIUM,
                         GameMode.HARD,
                         GameMode.JACKPOT]:
      raise InvalidGameMode("Invalid game mode entered")

    try:
      if game_mode == GameMode.JACKPOT:
        jackpot_on = self._promoDB.promo_switch.get()
        if not jackpot_on:
          revert("Maximum amount of Jackpots has been won, Promo is over, returning funds")
        if bet_amount != PROMO_ENTRY_VALUE:
          revert("Promo entry fee is 5 ICX")
        max_level = 6

      else:
        max_level = self._get_max_level(bet_amount, game_mode)

      # setup database access objects
      game_repository = IGameRepository(self._db)
      new_game_details = game_repository.create(player_address, bet_amount, datetime, max_level, game_mode)
      # trigger new game started event
      self.NewGameStarted(new_game_details)
    except BaseException as e:
      self.ShowException(str(e))
      revert(str(e))

  def _get_max_level(self, bet_amount: int, game_mode: int) -> int:
    per_level = self._get_max_bet_per_level(game_mode)

    if bet_amount <= int(per_level[0]):
      # able to play all levels (currently set at 6)
      return 6
    if int(per_level[0]) < bet_amount <= int(per_level[1]):
      return 5
    if int(per_level[1]) < bet_amount <= int(per_level[2]):
      return 4
    if int(per_level[2]) < bet_amount <= int(per_level[3]):
      return 3
    if int(per_level[3]) < bet_amount <= int(per_level[4]):
      return 2
    if int(per_level[4]) < bet_amount <= int(per_level[5]):
      return 1

    # if we get this far than we have an invalid bet amount so throw an error
    raise InvalidBetValue(f'Invalid bet value. bet value needs to be between {BET_MIN} and {int(per_level[5])}')

  def _get_treasury_min(self) -> int:
    treasury_min = self._roulette_score.get_treasury_min()
    return treasury_min

  def _get_game_details(self, player_address: Address, active_game_num: int) -> str:
    game_repository = IGameRepository(self._db)
    game_details = str(game_repository.get(player_address, active_game_num))
    return json_loads(game_details)

  def _get_open_games(self, player_address: Address) -> list:
    game_repository = IGameRepository(self._db)
    open_game_list = game_repository.get_open_games(player_address)
    return open_game_list

  def _select_tile(self, player_address: Address, active_game_num: int, square_id: int, user_seed: str):
    # this is the main betting function of the game
    # each call to the select_tile will pass in a square id (denoted by the number of tiles per row for that game mode
    # the function will then pass through a random function that will provide a random number based on hte number of
    # possible tiles per row
    # if the player tries to move to a new level and the random function lands on the number supplied by square_id
    # the play has effectively landed on a bomb and the game is over player loses the initial bet supplied
    # if the player lands on a bomb the player loses the initial bet supplied
    # the except to this rule is the HARD mode where if the player picks the tile the random number lands on then
    # it is considered the safe square since they are 2 bombs (out of 3) for HARD mode
    # if the player at any time lands on a safe square and is not on MAX_ROW_HEIGHT - 1 (second last row)
    # the player will increase in level
    # players are able to 'cash out' at at from level 1 onwards (except for jackpot mode)
    game_repository = IGameRepository(self.db)
    game = json_loads(game_repository.get(player_address, active_game_num))
    current_level = int(game["level"])
    game_max_height = int(game["max_level_allowed"])
    game_mode = game["game_mode"]
    bet_amount = int(game["bet_amount"])
    rake_amount = int(game["balance"])

    if active_game_num != game["active_game_num"]:
      raise InvalidGameException(
        f'active_game_num provided does not match any active_games initiated by player: active_game_num provided: {active_game_num}')

    # make sure the tile selection input is a number
    try:
      val = int(square_id)
    except ValueError:
      raise InvalidTileSelection("Must be an number")

    if game_mode == GameMode.JACKPOT:

      if square_id < 1 or square_id > MAX_BRICKS_PER_ROW:
        raise InvalidTileSelection("Select a number 1-4")

      jackpot_on = self._promoDB.promo_switch.get()
      if jackpot_on:
        # ---------------------
        # LOGIC FOR JACKPOT MODE
        # EASY MODE + LAST 2 LEVELS HAS 3 BOMBS
        # ----------------------
        random_number = int(self._get_random(MAX_BRICKS_PER_ROW, user_seed))
        # JACKPOT
        if current_level == 5 or current_level == 4:
          # we are now in the hard part of the game last 2 rows
          if square_id == random_number:
            # 1 step closer!
            new_level = current_level + 1
            if new_level == PROMO_MAX_ROW_HEIGHT:
              promo_wins = self._promoDB.promo_jackpot_wins.get() + 1
              self.SelectedSquareResult(random_number, "Congratulations you have won a JACKPOT!")
              try:
                # treat the game like a normal 2% game and get roughly half of the winnings from IB
                from_ib_treasury = bet_amount * float(PROMO_IB_TREASURY_MULTIPLIER)
                self._take_wager_and_payout(bet_amount, int(from_ib_treasury), rake_amount)
                # the promo part is we also give players another payout to make up the full 500ICX
                from_levels_treasury = bet_amount * float(PROMO_LEVELS_TREASURY_MULTIPLIER)
                self.icx.transfer(player_address, int(from_levels_treasury))
                game_repository.remove_from_active_game(player_address, active_game_num)
              except BaseException as e:
                revert(str(e))
              if promo_wins == 8:
                # turn promo off
                self._promoDB.promo_switch.set(False)
                # reset number of jackpot wins back to 0 for when we want to turn on a promo again
                self._promoDB.promo_jackpot_wins.set(0)
              else:
                self._promoDB.promo_jackpot_wins.set(promo_wins)
            else:
              new_level = current_level + 1
              game_repository.increase_level(player_address, active_game_num, random_number, square_id)
              self.SelectedSquareResult(random_number, f"SAFE! - You are now on level: {new_level}")
          else:
            self._take_wager(bet_amount, rake_amount)
            self.SelectedSquareResult(random_number, f"LOST! - Safe square was {random_number}")
            game_repository.remove_from_active_game(player_address, active_game_num)
        else:
          # lower levels
          if square_id == random_number:
            # player landed on bomb!
            self._take_wager(bet_amount, rake_amount)
            self.SelectedSquareResult(random_number, "LOST! - You landed on a Bomb!!")
            game_repository.remove_from_active_game(player_address, active_game_num)
          else:
            new_level = current_level + 1
            game_repository.increase_level(player_address, active_game_num, random_number, square_id)
            self.SelectedSquareResult(random_number, f"SAFE! - You are now on level: {new_level}")
      else:
        self.GenericMessage("Maximum amount of Jackpots has been won, Promo is over")
        game_repository.remove_from_active_game(player_address, active_game_num)

    # easy mode
    # 4 tiles per row
    # 1 bomb per row
    elif game_mode == GameMode.EASY:

      if square_id < 1 or square_id > MAX_BRICKS_PER_ROW:
        raise InvalidTileSelection("Select a number 1-4")

      random_number = int(self._get_random(MAX_BRICKS_PER_ROW, user_seed))
      if square_id == random_number:
        # player landed on bomb!
        self._take_wager(bet_amount, rake_amount)
        self.SelectedSquareResult(random_number, "LOST! - You landed on a Bomb!!")
        game_repository.remove_from_active_game(player_address, active_game_num)
      else:
        # player landed on a safe square!
        new_level = current_level + 1
        if new_level == game_max_height:
          self.SelectedSquareResult(random_number, "Congratulations you are a WINNER!")
          payout = bet_amount * float(ROW_MULTIPLIER[new_level])
          try:
            self._take_wager_and_payout(bet_amount, int(payout), rake_amount)
            game_repository.remove_from_active_game(player_address, active_game_num)
          except BaseException as e:
            Logger.debug(f'Send failed. Exception: {e}', TAG)
            revert(f'Network problem. Winnings not sent. Returning funds. {str(e)}')
        else:
          game_repository.increase_level_and_balance(player_address, active_game_num, random_number, square_id)
          self.SelectedSquareResult(random_number, f"SAFE! - you are now on level: {new_level}")

    # medium mode
    # 3 tiles per row
    # 1 bomb per row
    elif game_mode == GameMode.MEDIUM:

      if square_id < 1 or square_id > MEDIUM_MAX_BRICKS_PER_ROW:
        raise InvalidTileSelection("Select a number 1-3")

      random_number = int(self._get_random(MEDIUM_MAX_BRICKS_PER_ROW, user_seed))
      if square_id == random_number:
        # player landed on bomb!
        self._take_wager(bet_amount, rake_amount)
        self.SelectedSquareResult(random_number, "LOST! - You landed on a Bomb!!")
        game_repository.remove_from_active_game(player_address, active_game_num)
      else:
        # player landed on a safe square!
        new_level = current_level + 1
        if new_level == game_max_height:
          self.SelectedSquareResult(random_number, "Congratulations you are a WINNER!")
          payout = bet_amount * float(MEDIUM_ROW_MULTIPLIER[new_level])
          try:
            self._take_wager_and_payout(bet_amount, int(payout), rake_amount)
            game_repository.remove_from_active_game(player_address, active_game_num)
          except BaseException as e:
            Logger.debug(f'Send failed. Exception: {e}', TAG)
            revert(f'Network problem. Winnings not sent. Returning funds. {str(e)}')
        else:
          game_repository.increase_level_and_balance(player_address, active_game_num, random_number, square_id)
          self.SelectedSquareResult(random_number, f"SAFE! - you are now on level: {new_level}")

    # hard mode
    # 3 tiles per row
    # 2 bomb per row
    elif game_mode == GameMode.HARD:

      if square_id < 1 or square_id > HARD_MAX_BRICKS_PER_ROW:
        raise InvalidTileSelection("Select a number 1-3")

      random_number = int(self._get_random(HARD_MAX_BRICKS_PER_ROW, user_seed))
      if square_id == random_number:
        # player landed on a safe square!
        new_level = current_level + 1
        if new_level == game_max_height:
          self.SelectedSquareResult(random_number, "Congratulations you are a WINNER!")
          payout = bet_amount * float(HARD_ROW_MULTIPLIER[new_level])
          try:
            self._take_wager_and_payout(bet_amount, int(payout), rake_amount)
            game_repository.remove_from_active_game(player_address, active_game_num)
          except BaseException as e:
            Logger.debug(f'Send failed. Exception: {e}', TAG)
            revert(f'Network problem. Winnings not sent. Returning funds. {str(e)}')
        else:
          game_repository.increase_level_and_balance(player_address, active_game_num, random_number, square_id)
          self.SelectedSquareResult(random_number, f"SAFE! - you are now on level: {new_level}")
      else:
        # player landed on bomb!
        self._take_wager(bet_amount, rake_amount)
        self.SelectedSquareResult(random_number, "LOST! - You landed on a Bomb!!")
        game_repository.remove_from_active_game(player_address, active_game_num)

  def _process_cash_out(self, player_address: Address, active_game_num: int):
    game_repository = IGameRepository(self.db)
    game = json_loads(game_repository.get(player_address, active_game_num))
    game_mode = game["game_mode"]
    current_level = int(game["level"])
    bet_amount = int(game["bet_amount"])
    balance = int(game["balance"])
    rake_amount = 0

    if game_mode == GameMode.JACKPOT:
      revert("You are not able to cash out during a promo game")
    # check if the player is on the correct level to cash out

    if current_level > 0:
      # send accrued balance to player
      if current_level > 1:
        if game_mode == GameMode.EASY:
          rake_amount = bet_amount * float(ROW_MULTIPLIER[current_level - 1])
        elif game_mode == GameMode.MEDIUM:
          rake_amount = bet_amount * float(MEDIUM_ROW_MULTIPLIER[current_level - 1])
        elif game_mode == GameMode.HARD:
          rake_amount = bet_amount * float(HARD_ROW_MULTIPLIER[current_level - 1])
      try:
        self._take_wager_and_payout(bet_amount, balance, int(rake_amount))
        game_repository.remove_from_active_game(player_address, active_game_num)
      except BaseException as e:
        Logger.debug(f'Send failed. Exception: {e}', TAG)
        revert(str(e))
    else:
      raise InvalidLevelToCashOut(f'You are not allowed cash out at level: {current_level}')

  def _custom_bet(self, bet_amount: int, number_of_tiles: int, square_id: int, user_seed: str = '') -> None:
    self._valid_custom_game(number_of_tiles, square_id)

    if bet_amount < BET_MIN:
      revert(f'Invalid Min Bet: Min allowed is {BET_MIN}')

    max_bet_allowed = self._get_max_bet_custom_game(number_of_tiles)
    if bet_amount > max_bet_allowed:
      revert(f'Invalid Max Bet: Max allowed is {max_bet_allowed}')

    random_number = int(self._get_random(number_of_tiles, user_seed))
    payout = 0
    if square_id == random_number:
      # player landed on bomb!
      try:
        self._take_wager(bet_amount, 0)
        self.SelectedSquareResult(random_number, "LOST! - You landed on a Bomb!!")
      except BaseException as e:
        revert(f'Send failed. Exception: {e}')
    else:
      self.SelectedSquareResult(random_number, "Congratulations you are a WINNER!")
      if number_of_tiles == 8:
        payout = bet_amount * float(CUSTOM_MULTIPLIER[1])
      elif number_of_tiles == 12:
        payout = bet_amount * float(CUSTOM_MULTIPLIER[2])
      elif number_of_tiles == 16:
        payout = bet_amount * float(CUSTOM_MULTIPLIER[3])
      elif number_of_tiles == 20:
        payout = bet_amount * float(CUSTOM_MULTIPLIER[4])
      elif number_of_tiles == 24:
        payout = bet_amount * float(CUSTOM_MULTIPLIER[5])

      try:
        self._take_wager_and_payout(bet_amount, int(payout), 0)
      except BaseException as e:
        revert(f'Send failed. Exception: {e}')

  def _valid_custom_game(self, number_of_tiles: int, square_id: int) -> None:
    try:
      val = int(square_id)
    except ValueError:
      revert("Bet failed returning funds")
      raise InvalidTileSelection("Must be an number")

    try:
      val = int(number_of_tiles)
    except ValueError:
      revert("Number of tiles must be a number")

    if square_id < 1 or square_id > MAX_CUSTOM_BRICKS:
      revert("Select a number 1-24")

    if number_of_tiles not in [8, 12, 16, 20, 24]:
      revert("Number of tiles must be either 8, 12, 16, 20, 24")

    if square_id > number_of_tiles:
      revert("square selection is greater than number of tiles")

  def _get_max_bet_custom_game(self, number_of_tiles: int) -> int:
    _treasury_min = self._roulette_score.get_treasury_min()
    max_bet = 0
    if number_of_tiles == 8:
      max_bet = int((_treasury_min * 1.5 * 86) // (68134 - 681.34 * 86))
    elif number_of_tiles == 12:
      max_bet = int((_treasury_min * 1.5 * 88) // (68134 - 681.34 * 88))
    elif number_of_tiles == 16:
      max_bet = int((_treasury_min * 1.5 * 90) // (68134 - 681.34 * 90))
    elif number_of_tiles == 20:
      max_bet = int((_treasury_min * 1.5 * 92) // (68134 - 681.34 * 92))
    elif number_of_tiles == 24:
      max_bet = int((_treasury_min * 1.5 * 94) // (68134 - 681.34 * 94))

    return max_bet

  def _take_wager_and_payout(self, bet_amount: int, payout_amount: int, rake_amount: int) -> None:
    self.FundTransfer(self._iconBetDB.iconbet_score.get(), self.msg.value, "Sending icx to Roulette")
    # send wager to iconbet
    self.icx.transfer(self._iconBetDB.iconbet_score.get(), bet_amount)
    self._roulette_score.take_wager(bet_amount)
    if rake_amount > 0:
      self._roulette_score.take_rake(rake_amount, rake_amount)
    # send payout request to iconbet
    self._roulette_score.wager_payout(payout_amount)

  def _take_wager(self, bet_amount: int, rake_amount: int) -> None:
    self.FundTransfer(self._iconBetDB.iconbet_score.get(), self.msg.value, "Sending icx to Roulette")
    # send wager to iconbet
    self.icx.transfer(self._iconBetDB.iconbet_score.get(), bet_amount)
    self._roulette_score.take_wager(bet_amount)
    if rake_amount > 0:
      self._roulette_score.take_rake(rake_amount, rake_amount)

  def _get_random(self, brick_count: int, user_seed: str = '', ) -> int:
    # generates a random number between 1 - max options per bet
    seed = (str(bytes.hex(self.tx.hash)) + str(self.now()) + user_seed)
    brick = (int.from_bytes(sha3_256(seed.encode()), "big") % brick_count + 1) / 1
    return int(brick)

  def _get_max_bet_per_level(self, game_mode: int) -> list:
    _treasury_min = self._roulette_score.get_treasury_min()
    max_bet_level = list()

    if game_mode == GameMode.EASY:
      # level 6
      sixth_limit = int((_treasury_min * 1.5 * 17) // (68134 - 681.34 * 17))
      max_bet_level.append(sixth_limit)

      # level 5
      fifth_limit = int((_treasury_min * 1.5 * 23) // (68134 - 681.34 * 23))
      max_bet_level.append(fifth_limit)

      # level 4
      fourth_limit = int((_treasury_min * 1.5 * 31) // (68134 - 681.34 * 31))
      max_bet_level.append(fourth_limit)

      # level 3
      third_limit = int((_treasury_min * 1.5 * 42) // (68134 - 681.34 * 42))
      max_bet_level.append(third_limit)

      # level 2
      second_limit = int((_treasury_min * 1.5 * 56) // (68134 - 681.34 * 56))
      max_bet_level.append(second_limit)

      # level 1
      one_limit = int((_treasury_min * 1.5 * 75) // (68134 - 681.34 * 75))
      max_bet_level.append(one_limit)

    elif game_mode == GameMode.MEDIUM:
      # level 6
      sixth_limit = int((_treasury_min * 1.5 * 8) // (68134 - 681.34 * 8))
      max_bet_level.append(sixth_limit)

      # level 5
      fifth_limit = int((_treasury_min * 1.5 * 13) // (68134 - 681.34 * 13))
      max_bet_level.append(fifth_limit)

      # level 4
      fourth_limit = int((_treasury_min * 1.5 * 19) // (68134 - 681.34 * 19))
      max_bet_level.append(fourth_limit)

      # level 3
      third_limit = int((_treasury_min * 1.5 * 29) // (68134 - 681.34 * 29))
      max_bet_level.append(third_limit)

      # level 2
      second_limit = int((_treasury_min * 1.5 * 44) // (68134 - 681.34 * 44))
      max_bet_level.append(second_limit)

      # level 1
      one_limit = int((_treasury_min * 1.5 * 66) // (68134 - 681.34 * 66))
      max_bet_level.append(one_limit)

    elif game_mode == GameMode.HARD:
      # level 6
      sixth_limit = int((_treasury_min * 1.5 * 0.13) // (68134 - 681.34 * 0.13))
      max_bet_level.append(sixth_limit)

      # level 5
      fifth_limit = int((_treasury_min * 1.5 * 0.41) // (68134 - 681.34 * 0.41))
      max_bet_level.append(fifth_limit)

      # level 4
      fourth_limit = int((_treasury_min * 1.5 * 1.2) // (68134 - 681.34 * 1.2))
      max_bet_level.append(fourth_limit)

      # level 3
      third_limit = int((_treasury_min * 1.5 * 3) // (68134 - 681.34 * 3))
      max_bet_level.append(third_limit)

      # level 2
      second_limit = int((_treasury_min * 1.5 * 11) // (68134 - 681.34 * 11))
      max_bet_level.append(second_limit)

      # level 1
      one_limit = int((_treasury_min * 1.5 * 33) // (68134 - 681.34 * 33))
      max_bet_level.append(one_limit)

    return max_bet_level

  def _validate_action(self, action_model: dict) -> None:
    """
       Sanity checks for the action model passed in
       :param action_model: JSON metadata of the game
       :type action_model: dict
       :return:
     """
    valid_methods = ["create_new_game", "cash_out", "select_tile", "custom_bet"]
    method_name = action_model["name"]
    if method_name not in valid_methods:
      revert(f'There is no valid action method: {method_name} for this game')

  # ================================================
  #  External methods
  # ================================================
  @payable
  @external
  def action(self, model: str):
    if not self._iconBetDB.game_on.get():
      revert(f'DAOlevels game is turned off')

    action_model = json_loads(model)
    self._validate_action(action_model)
    method_name = action_model["name"]

    if method_name == "create_new_game":
      bet_amount = self.msg.value
      datetime = self.now()
      player_address = self.msg.sender
      game_mode = action_model["params"]["game_mode"]
      self._create_new_game(player_address, bet_amount, datetime, game_mode)

    if method_name == "select_tile":
      player_address = self.msg.sender
      active_game_num = action_model["params"]["active_game_num"]
      square_id = action_model["params"]["square_id"]
      user_seed = action_model["params"]["user_seed"]
      self._select_tile(player_address, active_game_num, square_id, user_seed)

    if method_name == "cash_out":
      player_address = self.msg.sender
      active_game_num = action_model["params"]["active_game_num"]
      self._process_cash_out(player_address, active_game_num)

    if method_name == "custom_bet":
      bet_amount = self.msg.value
      square_id = action_model["params"]["square_id"]
      user_seed = action_model["params"]["user_seed"]
      number_of_tiles = action_model["params"]["number_of_tiles"]
      self._custom_bet(bet_amount, number_of_tiles, square_id, user_seed)

  @external(readonly=True)
  def get_open_games_by_address(self, player_address: Address) -> list:
    return self._get_open_games(player_address)

  @external(readonly=True)
  def get_level_multipliers(self, game_mode: int = 0) -> str:
    if game_mode == GameMode.EASY:
      return json_dumps(ROW_MULTIPLIER)
    elif game_mode == GameMode.MEDIUM:
      return json_dumps(MEDIUM_ROW_MULTIPLIER)
    elif game_mode == GameMode.HARD:
      return json_dumps(HARD_ROW_MULTIPLIER)
    elif game_mode == GameMode.JACKPOT:
      return json_dumps(PROMO_ROW_MULTIPLIER)
    elif game_mode == GameMode.CUSTOM:
      return json_dumps(CUSTOM_MULTIPLIER)

  @external(readonly=True)
  def get_max_level_by_bet(self, bet_amount: int, game_mode: int = 0) -> int:
    return self._get_max_level(bet_amount, game_mode)

  @external(readonly=True)
  def get_max_bet_custom_game(self, number_of_tiles: int) -> int:
    return self._get_max_bet_custom_game(number_of_tiles)

  @external(readonly=True)
  def get_max_bet_allowed(self, game_mode: int = 0) -> str:
    if game_mode == GameMode.JACKPOT:
      li = [PROMO_ENTRY_VALUE, PROMO_ENTRY_VALUE, PROMO_ENTRY_VALUE, PROMO_ENTRY_VALUE, PROMO_ENTRY_VALUE,
            PROMO_ENTRY_VALUE]
      return json_dumps(li)
    return json_dumps(self._get_max_bet_per_level(game_mode))

  @external(readonly=True)
  def get_min_bet_allowed(self) -> int:
    return BET_MIN

  @external
  def set_roulette_score(self, score: Address) -> None:
    """
    Sets the roulette score address. The function can only be invoked by score owner.
    :param score: Score address of the roulette
    :type score: :class:`iconservice.base.address.Address`
    """

    if self.msg.sender == self.owner:
      self._iconBetDB.iconbet_score.set(score)

  @external(readonly=True)
  def get_roulette_score(self) -> Address:
    """
    Returns the roulette score address.
    :return: Address of the roulette score
    :rtype: :class:`iconservice.base.address.Address`
    """
    return self._iconBetDB.iconbet_score.get()

  @external
  def turn_game_on(self):
    game_admin = self._game_admin.get()
    if self.msg.sender != game_admin:
      revert('Only the game admin can call the game_on method')
    if not self._iconBetDB.game_on.get() and self._iconBetDB.iconbet_score.get() is not None:
      self._iconBetDB.game_on.set(True)

  @external
  def turn_game_off(self):
    game_admin = self._game_admin.get()
    if self.msg.sender != game_admin:
      revert('Only the game admin can call the game_on method')
    if self._iconBetDB.game_on.get():
     self._iconBetDB.game_on.set(False)

  @external
  def turn_promo_on(self) -> None:
    game_admin = self._game_admin.get()
    if self.msg.sender != game_admin:
      revert('Only the game admin can call the promo_on method')
    if not self._promoDB.promo_switch.get() and self._promoDB.promo_switch.get() is not None:
      self._promoDB.promo_switch.set(True)

  @external
  def turn_promo_off(self) -> None:
      game_admin = self._game_admin.get()
      if self.msg.sender != game_admin:
        revert('Only the game_admin can call the promo_off method')
      if self._promoDB.promo_switch.get():
        self._promoDB.promo_switch.set(False)

  @external(readonly=True)
  def get_promo_info(self) -> dict:
    promo_status = self._promoDB.promo_switch.get()
    promo_jackpot_amount = self._promoDB.promo_jackpot.get()
    promo_jackpot_wins = self._promoDB.promo_jackpot_wins.get()
    response = {
      'promo_entry_value': PROMO_ENTRY_VALUE,
      'promo_status': promo_status,
      'promo_jackpot_amount': promo_jackpot_amount,
      'bombs_per_level': PROMO_BOMBS_PER_LEVEL,
      'number_of_levels': PROMO_MAX_ROW_HEIGHT,
      'promo_win_amount': PROMO_WIN_AMOUNT,
      'number_of_promo_wins': promo_jackpot_wins
    }
    return response

  @payable
  @external
  def add_to_jackpot_promo(self) -> None:
    # anyone can add to the promo jackpot
    add_amount = self.msg.value
    current_jackpot_value = self._promoDB.promo_jackpot.get()
    self._promoDB.promo_jackpot.set(current_jackpot_value + add_amount)

  @external(readonly=True)
  def get_game_on_status(self) -> bool:
    return self._iconBetDB.game_on.get()

  @external(readonly=True)
  def get_score_owner(self) -> Address:
    """
    A function to return the owner of the score
    :return:Address
    """
    return self.owner

  @external
  def set_game_admin(self, admin_address: Address) -> None:
    if self.msg.sender != self.owner:
      revert('Only the owner can call set_game_admin method')
    self._game_admin.set(admin_address)

  @external(readonly=True)
  def get_game_admin(self) -> Address:
    """
    A function to return the admin of the game
    :return: Address
    """
    return self._game_admin.get()

  def fallback(self):
    pass
