# DO NOT UPLOAD THIS FILE WITH YOUR CREDENTIALS IN IT! TURN ON 2 FACTOR AUTHENTICATION JUST IN CASE!
rh = {
    'username': '123',
    'password': '123',
}
bnb = {
    'api_key': '123',
    'secret_key': '123',
}

# Modify these values to fit your trading strategy.
config = {
    'sellLimit': 0.01, # Percentage profit required to sell. 
    'movingAverageWindows': 20, # How many periods to consider for MA.
    'runMinute': [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58,], # What minute, on the minute, data will bre refreshed. (this is also when buy/sell conditions are checked and executed) 
    'coinList': ['BTCUSDT','MATICUSDT'], # options on Robinhood are currently DOGE, BTC, BSV, BCH, LTC, ETH, ETH
    'coinPair': ['BTC/USDT','MATIC/USDT'], # pairs separated by /
    'minutesBetweenUpdates': 2,
    'tradesEnabled': True, # When set to True, real buys/sells are possible. NOTE: This script currently lumps together positions you already own when selling a specific coin. So If you have 5 DOGE, and it buys 5 more... it will sell all 10 when sell condition is met!
    'rsiWindow': 10, # How many periods to consider for RSI.
}

