const socketio = io();
let userData;
let currentLobby;


///
// Login/logout stuff
///


$(".landingPage").addClass("show");

$(window).on("beforeunload", logout);

// Create account
$(".createAccount input[type='submit']").on("click", function() {
    event.preventDefault();
    data = {
        username: $(".createAccount .username").val(),
        password: $(".createAccount .password").val()
    };
    socketio.emit("createAccount", data)
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
        userData = data.userData
        login();
    }
});

// Login
$(".login input[type='submit']").on("click", function() {
    event.preventDefault();
    data = {
        username: $(".login .username").val(),
        password: $(".login .password").val()
    }
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

$(".logout").on("click", logout);

function login() {
    $(".landingPage").removeClass("show");
    $(".landingPage input:not([type='submit'])").val("");

    $(".pokerPage").addClass("show");
    $(".welcome").html("Welcome, " + userData.username + "!");
    $(".coins .numCoins").html(userData.coins);
    $(".level").html("Level " + userData.level);
}

function logout() {
    if (event) event.preventDefault();
    socketio.emit("logout");
    // leave all rooms

    $(".pokerPage").removeClass("show");
    $(".landingPage").addClass("show");

    userData = null;
}


///
// Joining lobbies
///


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
    data = {
        lobby: $(".playBox .createLobby .name").val()
    }
    socketio.emit("create", data)
})
socketio.on("create", function(data) {
    if (!data.success) {
        error("createLobby", data.message);
    } else {
        socketio.emit("createJoin", {lobby: data.lobby});
        joinLobby(data.lobby);
    }
});

// Join lobby
$(".playBox .joinLobby .join").on("click", function() {
    event.preventDefault();
    data = {
        lobby: $(".playBox .joinLobby .name").val()
    }
    socketio.emit("join", data);
})
socketio.on("join", function(data) {
    if (!data.success) {
        error("joinLobby", data.message);
    } else {
        socketio.emit("createJoin", {lobby: data.lobby});
        joinLobby(data.lobby);
    }
});

function joinLobby(lobby) {
    currentLobby = lobby;
    closePlayBox();
    $(".lobby").addClass("show");
    $(".lobby .lobbyName").html(lobby);
}

// Update list of user in lobby
socketio.on("updateUserList", function(data) {
    $(".players ul").html("");
    for (user in data.users) {
        if (user == userData.username && !data.users[user]) {
            $(".players ul").append($("<li>" + user + "<input type='submit' value='Ready up'></li>"));
            $(".players ul input").on("click", function() {
                event.preventDefault();
                socketio.emit("ready", {lobby: currentLobby});
            });
        } else {
            $(".players ul").append($("<li>" + user + "<span class='" + data.users[user] + "'></span></li>"));
        }
    }
    $(".players .true").html("ready");
    $(".players .false").html("not ready");
});