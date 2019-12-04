const socketio = io();
let userData;
let currentLobby;
let middlecard = 1;


$(".landingPage").addClass("show");

$(window).on("beforeunload", logout);

// Displays error message on a failed attempt to login
function error(type, message) {
    $("." + type + " .error").html(message);
    $("." + type + " .error").addClass("show");
    setTimeout(function() {
        $("." + type + " .error").removeClass("show");
    }, 1500);

    // add more logic to clear text fields
    if (message == "incorrect password") {
        $("." + type + " .input[type='password']").val("");
    } else if (message != "connection failed") {
        $("." + type + " input:not([type='submit'])").val("");
    }
}


//////////
//////////
// Login/logout stuff (and level up)
//////////
//////////


// Create account
$(".createAccount input[type='submit']").on("click", function() {
    event.preventDefault();
    data = {
        username: $(".createAccount .username").val(),
        password: $(".createAccount .password").val()
    };
    socketio.emit("createAccount", data);
});
socketio.on("createAccount", function(data) {
    if (!data.success) {
        if (data.exception) {
            error("createAccount", "connection failed");
            console.log(data.message);
        } else {
            error("createAccount", data.message);
        }
    } else {
        userData = data.userData;
        login();
    }
});

// Login
$(".login input[type='submit']").on("click", function() {
    event.preventDefault();
    data = {
        username: $(".login .username").val(),
        password: $(".login .password").val()
    };
    socketio.emit("login", data);
});
socketio.on("login", function(data) {
    if (!data.success) {
        if (data.exception) {
            error("login", "connection failed");
            console.log(data.message);
        } else {
            error("login", data.message);
        }
    } else {
        userData = data.userData;
        login();
    }
});

$(".logout").on("click", logout);

function login() {
    $(".landingPage").removeClass("show");
    $(".landingPage input:not([type='submit'])").val("");

    $(".pokerPage").addClass("show");
    $(".welcome").html("Welcome, " + userData.username + "!");
    $(".coins .numCoins").html(userData.coins);
    $(".numLevel").html("Level: " + userData.level);
}

function logout() {
    if (event) event.preventDefault();
    socketio.emit("logout");

    $(".lobby").removeClass("show");
    $(".pokerPage").removeClass("show");
    $(".game").removeClass("show");
    $(".landingPage").addClass("show");

    userData = null;
}

// Level up
$(".levelUp").on("click", function() {
    event.preventDefault();
    socketio.emit("levelUp");
});
socketio.on("levelUp", function(data) {
    if (!data.success) {
        if (data.exception) {
            error("level", "connection failed");
            console.log(data.message);
        } else {
            error("level", data.message);
        }
    }
});


//////////
//////////
// Joining lobbies
//////////
//////////


// Play box handlers
$(".play").on("click", function() {
    event.preventDefault();
    $(".playBox").addClass("show");
    $(".pokerPage *").not(".playBox, .playBox *").addClass("hide");
})

$(".playBox .cancel").on("click", closePlayBox);

function closePlayBox() {
    $(".playBox").removeClass("show");
    $(".pokerPage *").not(".playBox, .playBox *").removeClass("hide");
    setTimeout(function() {
        $(".playBox input[type='text']").val("");
    }, 1000);
}

// Create lobby
$(".playBox .createLobby .create").on("click", function() {
    event.preventDefault();
    socketio.emit("create", {lobby: $(".playBox .createLobby .name").val()})
})
socketio.on("create", function(data) {
    if (!data.success) {
        error("createLobby", data.message);
    } else {
        joinLobby(data.lobby);
    }
});

// Join lobby
$(".playBox .joinLobby .join").on("click", function() {
    event.preventDefault();
    socketio.emit("join", {lobby: $(".playBox .joinLobby .name").val()});
})
socketio.on("join", function(data) {
    if (!data.success) {
        error("joinLobby", data.message);
    } else {
        joinLobby(data.lobby);
    }
});

function joinLobby(lobby) {
    currentLobby = lobby;
    closePlayBox();
    $(".lobby").addClass("show");
    $(".game").removeClass("show");
    $(".lobby .lobbyName").html(lobby);
}

// Leave lobby
$(".playerList .leave").on("click", function() {
    event.preventDefault();
    leaveLobby();

    // Reset lobby
    $(".lobby").removeClass("show");
    $(".game").removeClass("show");
});

function leaveLobby() {
    socketio.emit("leave", {"lobby": currentLobby});
    closeBetBox();
}

// Update list of user in lobby
socketio.on("updateUserList", function(data) {
    $(".playerList ul").html("");
    for (user in data.users) {
        if (userData != null && user == userData.username && !data.users[user]) {
            $(".playerList ul").append($("<li>" + user + "<input type='submit' value='Ready up'></li>"));
            $(".playerList ul input").on("click", function() {
                event.preventDefault();
                data = {
                    AI: false,
                    lobby: currentLobby,
                    leave: false
                };
                socketio.emit("ready", data);
            });
        } else {
            $(".playerList ul").append($("<li>" + user + "<span class='" + data.users[user] + "'></span></li>"));
        }
    }
    $(".playerList .true").html("ready");
    $(".playerList .false").html("not ready");
});

// Update user coins
socketio.on("updateCoins", function(data) {
    $(".pokerPage .header .numCoins").html(data.amount);
});

// Update user level
socketio.on("updateLevel", function(data) {
    $(".pokerPage .header .numLevel").html("Level: " + data.level);
});


//////////
//////////
// Poker
//////////
//////////


// Display players and cards
socketio.on("startGame", function(data) {
    middleCard = 1;

    $(".game").addClass("show");
    $(".game > div").removeClass("show winner user");
    $(".game > div").removeClass("folded");
    $(".middleCards img").attr("src", "../static/cards/blank_card.jpg");

    playerNumber = 1;
    for (user in data.users) {
        if (user == userData.username) {
            $(".game .player" + playerNumber).addClass("user");
        } else {
            $(".game .player" + playerNumber + " .cards img").attr("src", "../static/cards/blank_card.jpg");
        }

        $(".game .player" + playerNumber + " h4").html(user);
        $(".game .player" + playerNumber).attr("data-username", user).addClass("show");
        playerNumber++;
    }
});

// Deal two cards to player
socketio.on("dealPlayer", function(data) {
    $(".game .user .card1").attr("src", "../static/cards/" + data.card1 + ".png");
    $(".game .user .card2").attr("src", "../static/cards/" + data.card2 + ".png");
});

// Deal middle cards
socketio.on("dealMiddle", function(data) {
    $.each(data, function(key, value) {
        $(".game .middleCards .card" + middleCard).attr("src", "../static/cards/" + value + ".png");
        middleCard++;
    }); 
});

// Betting
socketio.on("bet", function(data) {
    $(".betBox").addClass("show");
    if (data.amount > 0) {
        if (data.amount == 1) {
            $(".betBox .minBet").html(data.amount + " coin to stay in");
        } else {
            $(".betBox .minBet").html(data.amount + " coins to stay in");
        }
    }
    else {
        $(".betBox .minBet").html("");
    }
});

$(".betBox .bet").on("click", function() {
    event.preventDefault();
    data = {
        AI: false,
        fold: false,
        lobby: currentLobby,
        amount: $(".betBox .amount").val()
    };
    socketio.emit("bet", data);
});
socketio.on("betResponse", function(data) {
    if (!data.success) {
        if (data.exception) {
            error("betBox", "connection failed");
            console.log(data.message);
        } else {
            error("betBox", data.message);
        }
    } else {
        closeBetBox();
    }
});

function closeBetBox() {
    $(".betBox").removeClass("show");
    setTimeout(function() {
        $(".betBox .amount").val("");
    }, 1000);
}

// Fold
$(".betBox .fold").on("click", function() {
    event.preventDefault();
    data = {
        AI: false,
        lobby: currentLobby
    };
    socketio.emit("fold", data);
    closeBetBox();
});

// When anyone folds
socketio.on("newFold", function(data) {
    $(".game [data-username='" + data.user + "']").addClass("folded");
});

// When anyone bets
socketio.on("newBet", function(data) {
    $(".game [data-username='" + data.user + "'] .bet").html("Bet: " + data.amount);
});

// After round of betting
socketio.on("resetBets", function() {
    $(".game .bet").html("Bet: None");
});

// Update pot
socketio.on("updatePot", function(data) {
    $(".game .pot .amount").html(data.amount);
});

// End game -- display cards and winner
socketio.on("gameOver", function(data) {
    for (player in data.players) {
        $(".game [data-username='" + player + "'] .card1").attr("src", "../static/cards/" + data.players[player][0] + ".png");
        $(".game [data-username='" + player + "'] .card2").attr("src", "../static/cards/" + data.players[player][1] + ".png");
    };

    // Reveal winner
    for (player in data.winners) {
        $(".game [data-username='" + data.winners[player] + "']").addClass("winner");
    }
});

// Add AI
$(".addAI").on("click", function() {
    event.preventDefault();
    socketio.emit("addAI", {lobby: currentLobby});
});
// Kick AI
$(".kickAI").on("click", function() {
    event.preventDefault()
    socketio.emit("kickAI", {lobby: currentLobby});
});
socketio.on("aiResponse", function(data) {
    if (!data.success) {
        error("playerList", data.message);
    }
});