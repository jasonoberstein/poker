from flask import Flask, render_template, request, json
from flask_socketio import SocketIO, join_room, leave_room
import pymysql
pymysql.install_as_MySQLdb()
import MySQLdb
from passlib.hash import sha256_crypt
import random
import collections
import copy
import math

# Initialize stuff
app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = "Tejcxf17!!!"
socketio = SocketIO(app)


# Classes

# Cards
class Card:
    def __init__(self, value, suit):
        self.value = value
        self.suit = suit
    
    def display(self):
        return str(self.value) + "_of_" + str(self.suit)

# Games
class Game:
    def __init__(self, pot, deck, players, playerCards, playerBets, bluff):
        self.pot = pot
        self.deck = deck
        self.players = players
        self.playerCards = playerCards
        self.playerBets = playerBets
        self.bluff = bluff
        self.middleCards = None
        self.currentBetter = 0
        self.minBet = 0
        self.betStart = True
    
    def remove(self, player):
        self.players.remove(player)
        del self.playerCards[player]
        del self.playerBets[player]

# Deck
class Deck:
    def __init__(self):
        self.cards = [Card(value, suit) for value in range(2, 15) for suit in ["spades", "hearts", "diamonds", "clubs"]]
    
    def randomCard(self):
        card = random.choice(self.cards)
        self.cards.remove(card)
        return card

# Hand
class Hand:
    def __init__(self, player):
        self.type = None
        self.value1 = None
        self.value2 = None
        self.nextBest = None
        self.player = player


# Global variables
clients = {}
lobbies = {}
currentGames = {}
maxPlayers = 8
maxBet = 50 # Per betting round means max 200 coins per game
startingCoins = 1000
startingLevel = 5
levelUpCost = 300 # This number is scaled by the level. Going from 5 to 6 costs 5 * 300 = 1500

# AI globals
bluffChance = 20 # Chance of AI bluffing
stdDev = 0.05 * maxBet

# Database connection
def connect():
    conn = MySQLdb.connect( host="ec2-34-228-144-170.compute-1.amazonaws.com",
                            port=3306,
                            user="root",
                            password="Tejcxf17!",
                            database="poker")
    c = conn.cursor()
    return c, conn

# Load main page
@app.route("/")
def index():
	return render_template("index.html")


##########
##########
# Login/logout stuff
##########
##########


# Create account
@socketio.on("createAccount")
def createAccount(data):
    try:
        # Check for valid username and password
        if (data["username"] == "" or data["username"].find(" ") != -1 or data["password"] == ""):
            returnData = json.loads(json.dumps({
                "success": False,
                "message": "enter valid username and password"
            }))
        else:
            # Check if username is taken
            c, conn = connect()
            c.execute("SELECT username FROM users WHERE username=%s", data["username"])
            sqlData = c.fetchall()
            if len(sqlData) > 0:
                returnData = json.loads(json.dumps({
                    "success": False,
                    "message": "username already taken"
                }))
            else:
                # Create user
                c.execute("INSERT INTO users (username, password, coins, level) VALUES (%s, %s, %s, %s)", (data["username"], sha256_crypt.hash(data["password"]), startingCoins, startingLevel))
                conn.commit()

                # Need this query to get id of user
                c.execute("SELECT id, username, coins, level, password FROM users WHERE username=%s", (data["username"]))
                sqlData = c.fetchall()

                # Check if password matches (in case of multiple users with same username -- shouldn't happen, just being safe)
                for user in sqlData:
                    if sha256_crypt.verify(data["password"], user[4]):
                        # login
                        userData = json.loads(json.dumps({
                            "username": user[1],
                            "coins": user[2],
                            "level": user[3]
                        }))

                        clients[request.sid] = json.loads(json.dumps({
                            "id": user[0],
                            "username": user[1]
                        }))
                        
                        returnData = json.loads(json.dumps({
                            "success": True,
                            "userData": userData
                        }))
            c.close()
            conn.close()
    except Exception as e:
        returnData = json.loads(json.dumps({
            "success": False,
            "exception": True,
            "message": str(e)
        }))
    socketio.emit("createAccount", returnData, room = request.sid)

# Login to account
@socketio.on("login")
def login(data):
    try:
        # Look for user
        c, conn = connect()
        c.execute("SELECT id, username, coins, level, password FROM users WHERE username=%s", data["username"])
        sqlData = c.fetchall()
        c.close()
        conn.close()

        # Username doesn't match
        if len(sqlData) == 0:
            returnData = json.loads(json.dumps({
                "success": False,
                "message": "user does not exist"
            }))
        else:
            # Check if password matches
            match = False
            for user in sqlData:
                if sha256_crypt.verify(data["password"], user[4]):
                    # login
                    userData = json.loads(json.dumps({
                        "username": user[1],
                        "coins": user[2],
                        "level": user[3]
                    }))
                    
                    clients[request.sid] = json.loads(json.dumps({
                        "id": user[0],
                        "username": user[1]
                    }))

                    returnData = json.loads(json.dumps({
                        "success": True,
                        "userData": userData
                    }))
                    match = True
            
            if not match:
            # Password doesn't match
                returnData = json.loads(json.dumps({
                    "success": False,
                    "message": "incorrect password"
                }))
    except Exception as e:
        returnData = json.loads(json.dumps({
            "success": False,
            "exception": True,
            "message": str(e)
        }))
    socketio.emit("login", returnData, room = request.sid)

# Logout of account
@socketio.on("logout")
def logout():
    # Leave current lobby
    leaveData = None
    for currentLobby in lobbies:
        if request.sid in lobbies[currentLobby]:
            leaveData = json.loads(json.dumps({
                "lobby": currentLobby,
                "sid": request.sid
            }))
            break
    if not (leaveData == None):
        leave(leaveData)
        leave_room(leaveData["lobby"])
    
    # Delete user
    if request.sid in clients:
        del clients[request.sid]


##########
##########
# Joining lobbies
##########
##########


# Create lobby
@socketio.on("create")
def create(data):
    lobby = data["lobby"]
    if lobby == "":
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "enter a lobby name"
        }))
    elif lobby in lobbies:
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "lobby already exists"
        }))
    else:
        returnData = json.loads(json.dumps({
            "success": True,
            "lobby": lobby
        }))
        # Leave current lobby
        leaveData = getCurrentLobby(request.sid)
        if not (leaveData == None):
            leave(leaveData)
            leave_room(leaveData["lobby"])
        
        # Create lobby
        join_room(lobby)
        lobbies[lobby] = {request.sid: False}
        socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)
    
    socketio.emit("create", returnData, room = request.sid)

# Join lobby
@socketio.on("join")
def join(data):
    lobby = data["lobby"]
    if not (lobby in lobbies):
        # Lobby doesn't exist
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "lobby does not exist"
        }))
    elif request.sid in lobbies[lobby]:
        # Already in lobby
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "already in lobby"
        }))
    elif len(lobbies[lobby]) >= maxPlayers:
        # Too many players in lobby
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "lobby is full"
        }))
    elif lobby in currentGames:
        # Game already in play
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "game is already in session"
        }))
    else:
        # Success
        returnData = json.loads(json.dumps({
            "success": True,
            "lobby": lobby
        }))
        # Leave current lobby
        leaveData = getCurrentLobby(request.sid)
        if not (leaveData == None):
            leave(leaveData)
            leave_room(leaveData["lobby"])
        
        # Join lobby
        join_room(lobby)
        lobbies[lobby][request.sid] = False
        socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)
    
    socketio.emit("join", returnData, room = request.sid)

# Helper function, returns lobby user is in if any
def getCurrentLobby(sid):
    data = None
    for currentLobby in lobbies:
        if sid in lobbies[currentLobby]:
            data = json.loads(json.dumps({
                "lobby": currentLobby,
                "sid": sid
            }))
            break
    return data

# Ready up
@socketio.on("ready")
def ready(data):
    lobby = data["lobby"]
    if not (data["leave"] or data["AI"]):
        lobbies[lobby][request.sid] = True
        socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)

    # Check if all players are ready
    for user in lobbies[lobby]:
        if not lobbies[lobby][user]:
            return
    
    if not (lobby in currentGames) and len(lobbies[lobby]) > 1:
        # Start game
        players = []
        for user in lobbies[lobby]:
            players.append(user)

        socketio.emit("startGame", {"users": getUserList(lobby)}, room = lobby)
        startGame(lobby, players)

# Helper function, returns users in lobby
def getUserList(lobby):
    userList = {}
    for user in lobbies[lobby]:
        # username = ready or not ready (true or false)
        if user == "AI":
            userList["AI"] = True
        else:
            userList[clients[user]["username"]] = lobbies[lobby][user]
    return userList

# Leave lobby
@socketio.on("leave")
def leave(data):
    lobby = data["lobby"]
    if "sid" in data:
        sid = data["sid"]
    else:
        sid = request.sid

    # If in a game, fold
    if lobby in currentGames and sid in currentGames[lobby].players:
        foldData = json.loads(json.dumps({
            "AI": False,
            "lobby": lobby,
            "sid": sid
        }))
        fold(foldData)
    
    del lobbies[lobby][sid]

    readyData = json.loads(json.dumps({
        "AI": False,
        "lobby": lobby,
        "leave": True
    }))
    ready(readyData)

    # If lobby is empty, delete it
    if len(lobbies[lobby]) == 0 or len(lobbies[lobby]) == 1 and "AI" in lobbies[lobby]:
        del lobbies[lobby]

    else:
        # Update user list
        socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)


##########
##########
# Poker stuff
##########
##########


# Players is a list of socket ids
def startGame(lobby, players):
    # Ante up, ten coins each
    ante = 5 * len(players)
    # Subtract coins from database
    for player in players:
        if not (player == "AI"):
            c, conn = connect()
            c.execute("UPDATE users SET coins=coins-%s WHERE id=%s", (5, clients[player]["id"]))
            conn.commit()
            
            # Update front end coins
            c.execute("SELECT coins FROM users WHERE id=%s", clients[player]["id"])
            sqlData = c.fetchall()
            socketio.emit("updateCoins", {"amount": sqlData[0][0]}, room = player)
            
            c.close()
            conn.close()

    deck = Deck()
    playerCards = {}
    playerBets = {}

    # Deal two cards each
    for player in players:
        card1 = deck.randomCard()
        card2 = deck.randomCard()

        playerCards[player] = [card1, card2]
        playerBets[player] = 0

        if not (player == "AI"):
            socketio.emit("dealPlayer", {"card1": card1.display(), "card2": card2.display()}, room = player)
    
    # Does AI want to bluff?
    bluff = False if random.randint(0, 100) >= bluffChance else True

    # Create game to store information
    currentGames[lobby] = Game(ante, deck, players, playerCards, playerBets, bluff)
    socketio.emit("updatePot", {"amount": currentGames[lobby].pot}, room = lobby)

    # Have first player bet (order is random)
    better = currentGames[lobby].players[0]
    if better == "AI":
        betAI(lobby)
    else:
        socketio.emit("bet", {"amount": currentGames[lobby].minBet - currentGames[lobby].playerBets[better]}, room = better)
    return

# Player proposes a bet
@socketio.on("bet")
def bet(data):
    lobby = data["lobby"]
    if not (lobby in currentGames):
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "No current game"
        }))
    else:
        game = currentGames[lobby]
        fold = data["fold"]
        ai = data["AI"]

        if not fold:
            amount = data["amount"]
            betSuccess = False

            # Handle first round of bets
            if game.currentBetter == len(game.players) - 1:
                currentGames[lobby].betStart = False
            
            # Handle AI
            if ai:
                betSuccess = True
            else:
                # Not AI -- check if valid bet
                if not amount.isdigit():
                    returnData = json.loads(json.dumps({
                        "success": False,
                        "message": "enter a valid bet"
                    }))
                else:
                    amount = int(amount)

                    # Check if user's turn to bet
                    if (not game.players[game.currentBetter] == request.sid):
                        returnData = json.loads(json.dumps({
                            "success": False,
                            "message": "not your turn to bet"
                        }))
                    else:
                        # Check if bet is enough
                        if game.playerBets[request.sid] + amount < game.minBet:
                            returnData = json.loads(json.dumps({
                                "success": False,
                                "message": "bet more or fold"
                            }))
                        # Check if bet is too much
                        elif game.playerBets[request.sid] + amount > maxBet:
                            returnData = json.loads(json.dumps({
                                "success": False,
                                "message": "exceeds " + str(maxBet) + " coin limit"
                            }))
                        else:
                            # Check if user has sufficient funds
                            try:
                                c, conn = connect()
                                c.execute("SELECT coins FROM users WHERE id=%s", clients[request.sid]["id"])
                                sqlData = c.fetchall()
                                if amount > sqlData[0][0]:
                                    returnData = json.loads(json.dumps({
                                        "success": False,
                                        "message": "insufficient funds"
                                    }))
                                else:
                                    # Update database
                                    c.execute("UPDATE users SET coins=coins-%s WHERE id=%s", (amount, clients[request.sid]["id"]))
                                    conn.commit()

                                    # Update front end coins
                                    socketio.emit("updateCoins", {"amount": sqlData[0][0] - amount}, room = request.sid)

                                    returnData = json.loads(json.dumps({
                                        "success": True
                                    }))
                                    betSuccess = True
                                c.close()
                                conn.close()
                            except Exception as e:
                                returnData = json.loads(json.dumps({
                                    "success": False,
                                    "exception": True,
                                    "message": str(e)
                                }))
                socketio.emit("betResponse", returnData, room = request.sid)
        else:
            # Player folded -- continue betting
            betSuccess = True

        if betSuccess:
            # Update game
            if not fold:
                # Update who's turn it is and pot amount
                currentGames[lobby].currentBetter = (game.currentBetter + 1) % len(game.players)
                currentGames[lobby].pot += amount

                # Update player bets and minimum bet
                if ai:
                    currentGames[lobby].playerBets["AI"] += amount
                    currentGames[lobby].minBet = currentGames[lobby].playerBets["AI"]
                else:
                    currentGames[lobby].playerBets[request.sid] += amount
                    currentGames[lobby].minBet = currentGames[lobby].playerBets[request.sid]

                socketio.emit("updatePot", {"amount": currentGames[lobby].pot}, room = lobby)
            else:
                currentGames[lobby].currentBetter = game.currentBetter % len(game.players)

            # Check if all players have bet enough
            nextBet = False
            for player in currentGames[lobby].players:
                if not (currentGames[lobby].playerBets[player] == currentGames[lobby].minBet):
                    nextBet = True
                    break
            
            if nextBet or currentGames[lobby].betStart:
                # Update front end betting
                if not fold:
                    if ai:
                        socketio.emit("newBet", {"user": "AI", "amount": currentGames[lobby].playerBets["AI"]}, room = lobby)
                    else:
                        socketio.emit("newBet", {"user": clients[request.sid]["username"], "amount": currentGames[lobby].playerBets[request.sid]}, room = lobby)

                # Next bet
                better = game.players[currentGames[lobby].currentBetter]
                if better == "AI":
                    betAI(lobby)
                else:
                    socketio.emit("bet", {"amount": currentGames[lobby].minBet - currentGames[lobby].playerBets[better]}, room = better)
            else:
                # Reset current better, mininmum bet, and player bets
                currentGames[lobby].betStart = True
                currentGames[lobby].currentBetter = 0
                currentGames[lobby].minBet = 0
                for player in game.players:
                    currentGames[lobby].playerBets[player] = 0

                if game.middleCards == None or len(game.middleCards) < 5:
                    # Next round of betting
                    socketio.emit("resetBets", room = lobby)
                    better = currentGames[lobby].players[0]

                    if better == "AI":
                        betAI(lobby)
                    else:
                        socketio.emit("bet", {"amount": currentGames[lobby].playerBets[better]}, room = better)
                
                if game.middleCards == None:
                    # Deal three middle cards
                    card1 = currentGames[lobby].deck.randomCard()
                    card2 = currentGames[lobby].deck.randomCard()
                    card3 = currentGames[lobby].deck.randomCard()

                    currentGames[lobby].middleCards = [card1, card2, card3]
                    socketio.emit("dealMiddle", {"card1": card1.display(), "card2": card2.display(), "card3": card3.display()}, room = lobby)
                elif len(game.middleCards) < 5:
                    # Deal one middle card
                    card = currentGames[lobby].deck.randomCard()

                    currentGames[lobby].middleCards.append(card)
                    socketio.emit("dealMiddle", {"card": card.display()}, room = lobby)
                else:
                    finishGame(game, lobby, getWinners(game.playerCards, game.middleCards))

# Given all cards, compare the hands and select the winners
def getWinners(playerCards, middleCards):
    playerHands = []

    for player in playerCards:
        playerHands.append(getBestHand(middleCards + playerCards[player], player))

        # bestHand = Hand(player)
        # hand = middleCards + playerCards[player]
        # hand.sort(reverse = True, key = lambda card: card.value)

        # playerHands.append(bestHand)
    
    # We now have all hands stored in playerHands
    # Remove all lesser hands according to type
    bestType = 0
    for playerHand in playerHands:
        if playerHand.type > bestType:
            bestType = playerHand.type
    playerHands = [playerHand for playerHand in playerHands if playerHand.type == bestType]
    
    # Remove all lesser hands according to value1
    bestValue1 = 0
    if not (playerHands[0].value1 == None):
        bestValue1 = 0
        for playerHand in playerHands:
            if playerHand.value1 > bestValue1:
                bestValue1 = playerHand.value1
        playerHands = [playerHand for playerHand in playerHands if playerHand.value1 == bestValue1]
    
    # Remove all lesser hands according to value2
    bestValue2 = 0
    if not (playerHands[0].value2 == None):
        bestValue2 = 0
        for playerHand in playerHands:
            if playerHand.value2 > bestValue2:
                bestValue2 = playerHand.value2
        playerHands = [playerHand for playerHand in playerHands if playerHand.value2 == bestValue2]
    
    # Determine best hand based on next best cards
    if not (playerHands[0].nextBest == None):
        # Bubble up best hand
        for i in range (0, len(playerHands) - 1):
            if compareHands(playerHands[i].nextBest, playerHands[i+1].nextBest):
                # Swap
                playerHands[i], playerHands[i+1] = playerHands[i+1], playerHands[i]
        
        # This is best hand! Now check for other equivalent hands
        bestHands = [playerHands[len(playerHands) - 1]]
        for i in range (0, len(playerHands) - 1):
            if compareHands(playerHands[i].nextBest, bestHands[0].nextBest):
                bestHands.append(playerHands[i])
    else:
        bestHands = playerHands
    
    winners = []
    for playerHand in bestHands:
        winners.append(playerHand.player)
    return winners


##########
##########
# Helper functions
# for getting winner
##########
##########


def getBestHand(hand, player):
    bestHand = Hand(player)
    hand.sort(reverse = True, key = lambda card: card.value)

    # Count values
    values = collections.defaultdict(int)
    for card in hand:
        values[card.value] += 1
    
    # Check for pairs, three of a kind, and four of a kind
    groups = {"pairs": [], "threes": [], "fours": []}
    for value in values:
        if values[value] == 2:
            groups["pairs"].append(value)
        elif values[value] == 3:
            groups["threes"].append(value)
        elif values[value] == 4:
            groups["fours"].append(value)
    
    if len(groups["fours"]) == 1:
        four = groups["fours"][0]
        # 1=high card, 2=pair, 3=two pair, etc.
        bestHand.type = 8
        bestHand.value1 = four
        bestHand.nextBest = nextBestCards(hand, [four], 1)

    # If player has four of a kind, he can't do any better
    else:
        # Gather best pairs and best three of a kind
        three = None
        pair1 = None
        pair2 = None

        if len(groups["threes"]) > 0:
            # Choose best three of a kind
            groups["threes"].sort(reverse = True)
            three = groups["threes"][0]
        if len(groups["pairs"]) > 0:
            # Choose best two pairs
            groups["pairs"].sort(reverse = True)
            pair1 = groups["pairs"][0]
            if len(groups["pairs"]) > 1:
                pair2 = groups["pairs"][1]
        
        # Calculate best hand so far
        if not (pair2 == None):
            if not (three == None):
                bestHand.type = 7
                bestHand.value1 = three
                bestHand.value2 = pair1
                bestHand.nextBest = None
            else:
                bestHand.type = 3
                bestHand.value1 = pair1
                bestHand.value2 = pair2
                bestHand.nextBest = nextBestCards(hand, [pair1, pair2], 1)
        elif not (three == None):
            bestHand.type = 4
            bestHand.value1 = three
            bestHand.value2 = None
            bestHand.nextBest = nextBestCards(hand, [three], 2)
        elif not (pair1 == None):
            bestHand.type = 2
            bestHand.value1 = pair1
            bestHand.value2 = None
            bestHand.nextBest = nextBestCards(hand, [pair1], 3)
        else:
            bestHand.type = 1
            bestHand.value1 = None
            bestHand.value2 = None
            bestHand.nextBest = nextBestCards(hand, [], 5)

        # Calculate straight and flush
        # If full house or four of kind, this is the best the hand can do
        # since these cannot coexist with straight flushes
        if not (bestHand.type == 7 or bestHand.type == 8):
            # Check for straight -- must check permutations of 5 cards
            straight = None
            flush = None
            straightFlush = False
            for i in range(0, len(hand) - 1):
                if straightFlush:
                    break
                for j in range(i + 1, len(hand)):
                    # Look at hand
                    newHand = copy.deepcopy(hand)
                    newHand.reverse()
                    newHand[i] = "removeMe"
                    newHand[j] = "removeMe"
                    newHand.remove("removeMe")
                    newHand.remove("removeMe")
                    isStraight = True
                    isFlush = True
                    for k in range(0, len(newHand) - 1):
                        if not (newHand[k+1].value - newHand[k].value == 1):
                            isStraight = False
                        if not (newHand[k+1].suit == newHand[k].suit):
                            isFlush = False
                    
                    # edge case: 2, 3, 4, 5, ace
                    if newHand[0] == 2 and newHand[1] == 3 and newHand[2] == 4 and newHand[3] == 5 and newHand[4] == 14:
                        isStraight = True

                    if isStraight:
                        if straight == None:
                            # Best straight
                            straight = newHand[4].value
                        if isFlush:
                            # Best straight flush
                            straightFlush = True
                            bestHand.type = 9
                            bestHand.value1 = newHand[4].value
                            bestHand.value2 = None
                            bestHand.nextBest = None

                    if isFlush and flush == None:
                        # Best flush
                        flush = newHand[4].value

            if not (bestHand.type == 9):
                if not (straight == None):
                    bestHand.type = 5
                    bestHand.value1 = straight
                    bestHand.value2 = None
                    bestHand.nextBest = None
                if not (flush == None):
                    bestHand.type = 6
                    bestHand.value1 = flush
                    bestHand.value2 = None
                    bestHand.nextBest = None
    return bestHand

# Finds next best cards in sorted hand, in order, excluding values
def nextBestCards(hand, values, numCards):
    newHand = [card for card in hand if not (card.value in values)]
    
    returnHand = []
    for i in range(0, numCards):
        returnHand.append(newHand[i])
    return returnHand

# Compares hands based on values of cards
# Returns true if hand1 is at least as good as hand2
def compareHands(hand1, hand2):
    for i in range(0, len(hand1)):
        if (hand1[i].value < hand2[i].value):
            return False
    return True

# Distribute winnings and reset everything
def finishGame(game, lobby, winners):
    if not (len(lobbies[lobby]) == 1 and "AI" in lobbies[lobby]):
        # Distribute winnings
        winnings = math.floor(currentGames[lobby].pot / len(winners))
        returnWinners = []
        for winner in winners:
            if not (winner == "AI"):
                c, conn = connect()
                c.execute("UPDATE users SET coins=coins+%s WHERE id=%s", (winnings, clients[winner]["id"]))
                conn.commit()
                c.execute("SELECT coins FROM users WHERE id=%s", (clients[winner]["id"]))
                sqlData = c.fetchall()
                c.close()
                conn.close()

                # Update front end coins
                socketio.emit("updateCoins", {"amount": sqlData[0][0]}, room = winner)

                returnWinners.append(clients[winner]["username"])
            else:
                returnWinners.append("AI")
        
        # Reveal player cards
        returnPlayers = {}
        for player in game.playerCards:
            if not (player == "AI"):
                returnPlayers[clients[player]["username"]] = [game.playerCards[player][0].display(), game.playerCards[player][1].display()]

                # Update level if necessary
                levelDown(player)
            else:
                returnPlayers["AI"] = [game.playerCards[player][0].display(), game.playerCards[player][1].display()]

        # Unready everyone
        for player in lobbies[lobby]:
            if not (player == "AI"):
                lobbies[lobby][player] = False
        
        socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)
        socketio.emit("resetBets", room = lobby)
        socketio.emit("gameOver", {"players": returnPlayers, "winners": returnWinners}, room = lobby)

    # Kill game
    del currentGames[lobby]

# Folding
@socketio.on("fold")
def fold(data):
    lobby = data["lobby"]

    if data["AI"]:
        currentGames[lobby].remove("AI")
        socketio.emit("newFold", {"user": "AI"}, room = lobby)
    else:
        if "sid" in data:
            sid = data["sid"]
        else:
            sid = request.sid
        currentGames[lobby].remove(sid)

        # Update level if necessary
        levelDown(sid)

        socketio.emit("newFold", {"user": clients[sid]["username"]}, room = lobby)

    # If one person remains, that person wins
    game = currentGames[lobby]
    if len(game.players) == 1:
        finishGame(game, lobby, game.players)
    else:
        # Continue betting
        betData = json.loads(json.dumps({
            "AI": False,
            "fold": True,
            "lobby": lobby
        }))
        bet(betData)

# Level down player if coins are less than minimum
def levelDown(player):
    c, conn = connect()
    c.execute("SELECT coins, level FROM users WHERE id=%s", clients[player]["id"])
    sqlData = c.fetchall()
    coins = sqlData[0][0]
    level = sqlData[0][1]

    if coins < 4 * maxBet:
        # Not enough coins -- give coins
        c.execute("UPDATE users SET coins=coins+%s WHERE id=%s", (startingCoins, clients[player]["id"]))
        conn.commit()
        socketio.emit("updateCoins", {"amount": coins + startingCoins}, player)

        if level > 1:
            # Level down
            c.execute("UPDATE users SET level=level-1 WHERE id=%s", clients[player]["id"])
            conn.commit()
            socketio.emit("updateLevel", {"level": level - 1}, player)
    
    c.close()
    conn.close()

# Level up
@socketio.on("levelUp")
def levelUp():
    try:
        c, conn = connect()
        c.execute("SELECT coins, level FROM users WHERE id=%s", clients[request.sid]["id"])
        sqlData = c.fetchall()
        coins = sqlData[0][0]
        level = sqlData[0][1]
        fundsNeeded = level * levelUpCost + 4 * maxBet

        # Check if user has sufficient funds
        if coins < fundsNeeded:
            returnData = json.loads(json.dumps({
                "success": False,
                "message": str(fundsNeeded) + " coins required"
            }))
        else:
            # Update level and subtract coins
            c.execute("UPDATE users SET level=level+1, coins=coins-%s WHERE id=%s", (level * levelUpCost, clients[request.sid]["id"]))
            conn.commit()

            returnData = json.loads(json.dumps({
                "success": True
            }))
            # Update front end
            socketio.emit("updateLevel", {"level": level + 1}, request.sid)
            socketio.emit("updateCoins", {"amount": coins - level * levelUpCost}, request.sid)
        
        c.close()
        conn.close()
    except Exception as e:
        returnData = json.loads(json.dumps({
            "success": False,
            "exception": True,
            "message": str(e)
        }))
    socketio.emit("levelUp", returnData, request.sid)


##########
##########
# AI stuff
##########
##########


# Add an AI to the lobby
@socketio.on("addAI")
def addAI(data):
    lobby = data["lobby"]
    if not (lobby in lobbies):
        return
    
    # Check if AI is already in lobby
    if "AI" in lobbies[lobby]:
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "AI already present"
        }))
        socketio.emit("aiResponse", returnData, request.sid)
        return
    elif len(lobbies[lobby]) >= maxPlayers:
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "lobby is full"
        }))
        socketio.emit("aiResponse", returnData, request.sid)
        return

    # AI is always ready
    lobbies[lobby]["AI"] = True
    socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)

    readyData = json.loads(json.dumps({
        "AI": True,
        "lobby": lobby,
        "leave": False
    }))
    ready(readyData)

# Kick AI from the lobby
@socketio.on("kickAI")
def kickAI(data):
    lobby = data["lobby"]
    if not (lobby in lobbies):
        return
    
    # Check if no AI in lobby
    if not ("AI" in lobbies[lobby]):
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "No AI present"
        }))
    else:
        # Check if in game
        if lobby in currentGames:
            returnData = json.loads(json.dumps({
                "success": False,
                "message": "Game in progress"
            }))
        else:
            returnData = json.loads(json.dumps({
                "success": True
            }))
            del lobbies[lobby]["AI"]
            socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)
    socketio.emit("aiResponse", returnData, room = request.sid)

# Decides how much AI should bet
# Draws from various normal distributions
# Lots of arbitrary constants that I thought would work well
def betAI(lobby):
    game = currentGames[lobby]

    # Bluff
    bluffAdjust = 0
    if game.bluff:
        bluffAdjust = 0.2

    if game.middleCards == None:
        # Bet based on two cards
        dummyCards = []
        for i in range(0, 5):
            dummyCards.append(Card(-100 * i, "dummy" + str(i)))
        bestHand = getBestHand(game.playerCards["AI"] + dummyCards, "AI")

        # Handle first bet more carefully than others
        if bestHand.type == 2:
            if bestHand.value1 > 7:
                # Bet alot
                targetBet = int(random.normalvariate((0.7 + bluffAdjust) * maxBet, stdDev))
            else:
                # Bet a fair amount
                targetBet = int(random.normalvariate((0.4 + bluffAdjust) * maxBet, stdDev))
        else:
            # Don't bet that much
            targetBet = int(random.normalvariate((0.2 + bluffAdjust) * maxBet, stdDev))
        
        # AI becomes more resistant to folding as the game progresses
        stubbornness = 85
    
    elif len(game.middleCards) == 3:
        # Bet based on five cards
        dummyCards = []
        for i in range(0, 2):
            dummyCards.append(Card(-100 * i, "dummy" + str(i)))
        bestHand = getBestHand(game.playerCards["AI"] + game.middleCards + dummyCards, "AI")

        targetBet = int(random.normalvariate((((bestHand.type + 2) / 10) + bluffAdjust) * maxBet, stdDev))
        stubbornness = 90
    
    elif len(game.middleCards) == 4:
        # Bet based on six cards
        dummyCards = [Card(-100, "dummy")]
        bestHand = getBestHand(game.playerCards["AI"] + game.middleCards + dummyCards, "AI")

        targetBet = int(random.normalvariate((((bestHand.type + 2) / 10) + bluffAdjust) * maxBet, stdDev))
        stubbornness = 95
    
    else:
        # Bet based on seven cards
        bestHand = getBestHand(game.playerCards["AI"] + game.middleCards, "AI")

        targetBet = int(random.normalvariate((((bestHand.type + 2) / 10) + bluffAdjust) * maxBet, stdDev))
        stubbornness = 95
    
    # Is the hand terrible?
    badHand = True if bestHand.type == 1 and game.playerCards["AI"][0].value + game.playerCards["AI"][1].value < 10 else False

    tooRich = False
    idealBet = targetBet - game.playerBets["AI"]
    if targetBet > maxBet:
        # Bet the maximum allowed
        finalBet = maxBet - game.playerBets["AI"]
    elif targetBet >= game.minBet:
        # Bet perfect amount
        finalBet = idealBet
    else:
        # Must bet more than ideal to stay in
        # Want folding to be unlikely

        # Normalized difference in bets
        diff = (game.minBet - targetBet) / maxBet
        rand = random.randint(0,100)
        if diff < 0.4 or rand <= stubbornness and not badHand:
            # Stay in
            finalBet = game.minBet - game.playerBets["AI"]
        else:
            # Fold
            finalBet = None
            tooRich = True

    if tooRich:
        foldData = json.loads(json.dumps({
            "AI": True,
            "lobby": lobby,
        }))
        fold(foldData)
    else:
        betData = json.loads(json.dumps({
            "AI": True,
            "fold": False,
            "lobby": lobby,
            "amount": finalBet
        }))
        bet(betData)


##########
##########
# Run app
##########
##########
if __name__ == "__main__":
    socketio.run(app)