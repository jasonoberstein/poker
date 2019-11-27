from flask import Flask, render_template, request, json, session
from flask_session import Session
from redis import Redis
from flask_socketio import SocketIO, join_room, leave_room
import pymysql
pymysql.install_as_MySQLdb()
import MySQLdb
from passlib.hash import sha256_crypt

# Initialize stuff
app = Flask(__name__, template_folder="templates")
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
socketio = SocketIO(app)

# Global variables
lobbies = {}
maxPlayers = 8

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
                        
                        session[request.sid] = json.loads(json.dumps({
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
                    
                    session[request.sid] = json.loads(json.dumps({
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
    session.pop(request.sid)


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
        # Make this a dictionary?
        lobbies[lobby][session.get(request.sid)["username"]] = False
    else:
        lobbies[lobby] = {session.get(request.sid)["username"]: False}
    join_room(lobby)
    socketio.emit("updateUserList", {"users": lobbies[lobby]}, room = lobby)

@socketio.on("ready")
def onReady(data):
    lobby = data["lobby"]
    lobbies[lobby][session.get(request.sid)["username"]] = True
    socketio.emit("updateUserList", {"users": lobbies[lobby]}, room = lobby)

    # Check if all players are ready
    for user in lobbies[lobby]:
        if not lobbies[lobby][user]:
            return
    
    if len(lobbies[lobby]) > 1:
        # Start game
        players = []
        for user in lobbies[lobby]:
            players.append(user)
        startGame(players)


###
# Poker stuff
###


def startGame(players):
    print(players)


###
# Run app
###
if __name__ == "__main__":
    socketio.run(app)