from flask import Flask, render_template, request, json
from flask_socketio import SocketIO, join_room, leave_room
import pymysql
pymysql.install_as_MySQLdb()
import MySQLdb
from passlib.hash import sha256_crypt
import random
import copy

# Initialize stuff
app = Flask(__name__, template_folder="templates")
socketio = SocketIO(app)

# Cards
class Card:
    def __init__(self, value, suit):
        self.value = value
        self.suit = suit
    
    def display():
        return value + " of " + suit

# Games
class Game:
    def __init__(self, pot, deck, playerCards, currentBetter):
        self.pot = pot
        self.deck = deck
        self.playerCards = playerCards
        self.middleCards = None
        self.currentBetter = currentBetter
        self.minBet = 0


# Global variables
clients = {}
lobbies = {}
currentGames = {}
maxPlayers = 8
deck = [Card(value, suit) for value in range(1, 14) for suit in ["spades", "hearts", "diamonds", "clubs"]]

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


###
# Login/logout stuff
###


@socketio.on("createAccount")
def createAccount(data):
    try:
        c, conn = connect()

        # Check for valid username and password
        if (data["username"] == "" or data["username"].find(" ") != -1 or data["password"] == ""):
            returnData = json.loads(json.dumps({
                "success": False,
                "message": "enter valid username and password"
            }))
        else:
            # Check if username is taken
            c.execute("SELECT username FROM users WHERE username=%s", data["username"])
            sqlData = c.fetchall()
            if len(sqlData) > 0:
                returnData = json.loads(json.dumps({
                    "success": False,
                    "message": "username already taken"
                }))
            else :
                # Create user
                c.execute("INSERT INTO users (username, password, coins, level) VALUES (%s, %s, %s, %s)", (data["username"], sha256_crypt.encrypt(data["password"]), 1000, 1))
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
    except Exception as e:
        returnData = json.loads(json.dumps({
            "success": False,
            "exception": True,
            "message": str(e)
        }))
    socketio.emit("createAccount", returnData, room = request.sid)

@socketio.on("login")
def login(data):
    try:
        c, conn = connect()

        # Look for user
        c.execute("SELECT id, username, coins, level, password FROM users WHERE username=%s", data["username"])
        sqlData = c.fetchall()

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
            
            if (not match):
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

@socketio.on("logout")
def logout():
    del clients[request.sid]


###
# Joining lobbies
###


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
    
    socketio.emit("create", returnData, room = request.sid)

@socketio.on("join")
def join(data):
    lobby = data["lobby"]
    if not (lobby in lobbies):
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "lobby does not exist"
        }))
    else:
        returnData = json.loads(json.dumps({
            "success": True,
            "lobby": lobby
        }))
    
    socketio.emit("join", returnData, room = request.sid)

@socketio.on("createJoin")
def onJoin(data):
    lobby = data["lobby"]
    if (lobby in lobbies):
        lobbies[lobby][request.sid] = False
    else:
        lobbies[lobby] = {request.sid: False}
    join_room(lobby)
    socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)

@socketio.on("ready")
def onReady(data):
    lobby = data["lobby"]
    lobbies[lobby][request.sid] = True
    socketio.emit("updateUserList", {"users": getUserList(lobby)}, room = lobby)

    # Check if all players are ready
    for user in lobbies[lobby]:
        if not lobbies[lobby][user]:
            return
    
    if len(lobbies[lobby]) > 1:
        # Start game
        players = []
        for user in lobbies[lobby]:
            players.append(user)

        socketio.emit("startGame", {"users": getUserList(lobby)}, room = lobby)
        startGame(lobby, players)

def getUserList(lobby):
    userList = {}
    for user in lobbies[lobby]:
        # username = ready or not ready (true or false)
        userList[clients[user]["username"]] = lobbies[lobby][user]
    return userList


###
# Poker stuff
###


# Players is a list of socket ids
def startGame(lobby, players):
    # Ante up, ten coins each
    ante = 10 * len(players)
    #get coins from database

    gameDeck = copy.deepcopy(deck)
    playerCards = {}

    # Deal two cards each
    for player in players:
        card1 = random.choice(gameDeck)
        gameDeck.remove(card1)
        card2 = random.choice(gameDeck)
        gameDeck.remove(card2)

        playerCards[player] = [card1, card2]
        socketio.emit("dealPlayer", {"player": clients[player]["username"],
                                    "card1Value": card1.value, "card1Suit": card1.suit,
                                    "card2Value": card2.value, "card2Suit": card2.suit}, room = lobby)

    # Create game to store information
    currentGames[lobby] = Game(ante, gameDeck, playerCards, players[0])

    # Have first player bet (order is random)
    socketio.emit("bet", room = players[0])
    return

@socketio.on("bet")
def bet(data):
    lobby = data["lobby"]
    amount = data["amount"]
    game = currentGames[lobby]
    
    # Check if valid bet
    if not amount.isdigit():
        returnData = json.loads(json.dumps({
            "success": False,
            "message": "Enter a valid bet"
        }))
    else:
        amount = int(amount)

        # Check if user's turn to bet
        if (not (game.currentBetter == request.sid)):
            returnData = json.loads(json.dumps({
                "success": False,
                "message": "Not your turn to bet"
            }))
        else:
            # Check if bet is enough
            if (amount < game.minBet):
                returnData = json.loads(json.dumps({
                    "success": False,
                    "message": "Bet more or fold"
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
                            "message": "Insufficient funds"
                        }))
                    else:
                        # Update database
                        c.execute("UPDATE users SET coins=%s WHERE id=%s", (sqlData[0][0] - amount, clients[request.sid]["id"]))
                        conn.commit()

                        returnData = json.loads(json.dumps({
                            "success": True
                        }))
                except Exception as e:
                    returnData = json.loads(json.dumps({
                        "success": False,
                        "exception": True,
                        "message": str(e)
                    }))
    socketio.emit("betResponse", returnData, room = request.sid)


@socketio.on("test")
def test():
    socketio.emit("test", {"id": request.sid, "lobbies": lobbies}, room = request.sid)
    return


###
# Run app
###
if __name__ == "__main__":
    socketio.run(app)