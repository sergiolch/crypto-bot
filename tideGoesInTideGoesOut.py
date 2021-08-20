import pickle
import os.path as path
import os
import datetime
import time
import pandas as pd
import math
from binance.client import Client
import tideconfig as cfg
import talib

class coin:
    purchasedPrice = 0.0
    numHeld = 0.0
    numBought = 0.0
    name = ''
    lastBuyOrder = ''
    timeBought = ''
    fee_maker = 0.0
    fee_taker = 0.0

    def __init__(self, name=''):
        print('Creating coin ' + name)
        self.name = name
        self.purchasedPrice = 0.0
        self.numHeld = 0.0
        self.numBought = 0.0
        self.lastBuyOrderID = ''
        self.timeBought = ''

class moneyBot:

    # set these in tideconfig.py
    tradesEnabled = False
    buyBelowMA = 0.00
    sellAboveBuyPrice = .00
    movingAverageWindows = 0
    rsiWindow = 0
    runMinute = []
    coinList = []
    coinPair = []
    coinState = []
    minIncrements = {}  # the smallest increment of a coin you can buy/sell
    minPriceIncrements = {}   # the smallest fraction of a dollar you can buy/sell a coin with
    data = pd.DataFrame()
    boughtIn = False
    client = False

    # used to determine if we have had a break in our incoming price data and hold buys if so
    minutesBetweenUpdates = 0
    buysLockedCounter = 0
    minConsecutiveSamples = 0
    pricesGood = False

    def __init__(self):

        self.loadConfig()
        if not os.path.exists('data'):
            os.makedirs('data')

        if path.exists('data/state.pickle'):
            # load state
            print('Saved state found, loading.')
            with open('data/state.pickle', 'rb') as f:
                self.coinState = pickle.load(f)

            with open('data/boughtIn.pickle', 'rb') as f:
                self.boughtIn = pickle.load(f)

        else:

            # create state storage object
            print('No state saved, starting from scratch.')
            self.coinState = []
            for c in self.coinList:
                print(c)
                self.coinState.append(coin(c))

        self.data = self.loadDataframe()
        if not self.client:
            self.client = Client(self.bnb_api_key, self.bnb_secret_key)
        self.getIncrements()

        return

    def loadConfig(self):
        print('\nLoading Config...')
        self.rh_user = cfg.rh['username']
        self.rh_pw = cfg.rh['password']
        self.bnb_api_key = cfg.bnb['api_key']
        self.bnb_secret_key = cfg.bnb['secret_key']
        self.sellAboveBuyPrice = float(cfg.config['sellLimit'])
        print('Sell Limit ' + str(self.sellAboveBuyPrice * 100) + '%')
        self.movingAverageWindows = cfg.config['movingAverageWindows']
        self.runMinute = cfg.config['runMinute']
        self.coinList = cfg.config['coinList']
        self.coinPair = cfg.config['coinPair']
        self.tradesEnabled = cfg.config['tradesEnabled']
        print('Trades enabled: ' + str(self.tradesEnabled))
        self.rsiWindow = cfg.config['rsiWindow']
        print('RSI Window: ' + str(self.rsiWindow))
        print('MA Window: ' + str(self.movingAverageWindows))
        self.minutesBetweenUpdates = cfg.config['minutesBetweenUpdates']

        if self.rsiWindow > self.movingAverageWindows:
            self.minConsecutiveSamples = self.rsiWindow
        else:
            self.minConsecutiveSamples = self.movingAverageWindows
        print('Consecutive prices required: ' + str(self.minConsecutiveSamples))

        print('\n')

    def getPrices(self):

        prices = {}
        emptyDict = {}

        for c in self.coinList:
            try:
                result = self.client.get_ticker(symbol=c)
                price = (float(result['askPrice'])-float(result['bidPrice']))/2
            except:
                print('An exception occurred retrieving prices.')
                return emptyDict

            prices.update({c: float(price)})

        return prices

    def saveState(self):
        # save state
        with open('data/state.pickle', 'wb') as f:
            pickle.dump(self.coinState, f)

        with open('data/boughtIn.pickle', 'wb') as f:
            pickle.dump(self.boughtIn, f)

        self.data.to_pickle('data/dataframe.pickle')

    def getHoldings(self, ticker):
        # this contains the amount we currently own by id and code
        # quantity_available may be better
        quantity = 0.0
        try:
            result = self.client.get_open_orders()
            for t in range(0, len(result)):
                symbol = result[t]['symbol']
                if (symbol == ticker):
                    quantity = result[t]['origQty']
        except:
            print('Got exception while getting holdings from Binance.')
            quantity = -1.0

        return float(quantity)

    def getCash(self):

        # if you only want to trade part of your money, set this to (Available Cash - Amount to Trade)
        reserve = 0.2 # every time it buys, it will use 20% of current avavilable RH balance

        try:
            account = self.client.get_account()
            prices = self.client.get_all_tickers()
            cash = 0
            for acc in account['balances']:
                for price in prices:
                    if price['symbol']==acc['asset']:
                        cash = cash + (float(price['price'])*float(acc['free']))
                        break
        except:
            print('An exception occurred getting cash amount.')
            return -1.0

        if cash * reserve < 0.0:
            return 0.0
        else:
            print('Liquid cash: ' + str(cash))
            return cash * reserve

    def getCashAsset(self, c):

        # if you only want to trade part of your money, set this to (Available Cash - Amount to Trade)
        reserve = 0.2 # every time it buys, it will use 20% of current avavilable RH balance

        try:
            asset = ''
            for idx in range(len(self.coinList)):
                if c==self.coinList[idx]:
                    asset = self.coinPair[idx].split('/')[1]
                    break
            account = self.client.get_asset_balance(asset=asset)
            cash = float(account['free'])
        except:
            print('An exception occurred getting cash amount.')
            return -1.0

        if cash * reserve < 0.0:
            return 0.0
        else:
            print('Liquid cash: ' + str(cash))
            return cash * reserve

    def sell(self, c, price):

        if self.boughtIn == False:
            print('Previous sale incomplete.')
            return

        coinHeld = self.getHoldings(self.coinState[c].name)

        if coinHeld == -1:
            print('Got exception trying to get holdings in sell(), cancelling.')
            return

        print('Binance says you have ' + str(coinHeld) + ' of ' + str(self.coinState[c].name))

        if(coinHeld > 0.0):
            # price needs to be specified to no more precision than listed in minPriceIncrement. Truncate to 7 decimal places to avoid floating point problems way out at the precision limit
            minPriceIncrement = self.minPriceIncrements[self.coinState[c].name]
            price = round(self.roundDown(price, minPriceIncrement), 7)
            profit = (coinHeld * price) - (coinHeld * self.coinState[c].purchasedPrice)

            if self.tradesEnabled == True:

                try:
                    sellResult = self.client.order_limit_sell(symbol=str(self.coinList[c]), quantity=coinHeld, price=price)
                    self.coinState[c].lastSellOrder = sellResult['orderId']
                    print(str(sellResult))
                except:
                    print('Got exception trying to sell, cancelling.')
                    return

                print('Trades enabled. Sold ' + str(coinHeld) + ' of ' + str(self.coinList[c]) + ' at price ' + str(price) + ' profit ' + str(round(profit, 2)))


                self.coinState[c].purchasedPrice = 0.0
                self.coinState[c].numHeld = 0.0
                self.coinState[c].numBought = 0.0
                self.coinState[c].lastBuyOrderID = ''
                self.coinState[c].timeBought = ''
                self.boughtIn = False
            else:
                print('Trades not enabled. Would have sold ' + str(coinHeld) + ' of ' + str(self.coinList[c]) + ' at price ' + str(price) + ' profit ' + str(round(profit, 2)))

        return

    def buy(self, c, price):

        # we are already in the process of a buy, don't submit another
        if self.boughtIn == True:
            print('Previous buy incomplete.')
            return
        # swapping to this enables multi poistions, but the coin num held needs to be fixed as it is not currently cumulative. For me, if i buy in and the price continues to drop and meet my requirements, I would like to buy more to, and average the buy prices together to get my final sale price of the whole lot.
        # if self.coinState[c].numHeld > 0.0:
        #     print('Already holding ' + self.coinState.name + '. Let\'s resolve that position first.')
        #     return


        availableCash = self.getCashAsset(c)
        if availableCash == -1:
            print('Got an exception checking for available cash, canceling buy.')
            return

        print('Binance says you have ' + str(availableCash) + ' in cash')

        if (availableCash > 1.0):
            minPriceIncrement = self.minPriceIncrements[self.coinState[c].name]
            # price needs to be specified to no more precision than listed in minPriceIncrement. Truncate to 7 decimal places to avoid floating point problems way out at the precision limit
            price = round(self.roundDown(price, minPriceIncrement), 7)
            shares = (availableCash - .25)/price
            minShareIncrement = self.minIncrements[self.coinState[c].name]
            shares = round(self.roundDown(shares, minShareIncrement), 8)
            sellAt = price + (price * self.sellAboveBuyPrice)
            print('Buying ' + str(shares) + ' shares of ' + self.coinList[c] + ' at ' + str(price) + ' selling at ' + str(round(sellAt, 2)))

            if self.tradesEnabled == True:
                try:
                    buyResult = self.client.order_limit_buy(symbol=str(self.coinList[c]), quantity=shares, price=price)
                    self.coinState[c].lastBuyOrderID = buyResult['orderId']
                    print(str(buyResult))
                except:
                    print('Got exception trying to buy, cancelling.')
                    return

                print('Bought ' + str(shares) + ' shares of ' + self.coinList[c] + ' at ' + str(price) + ' selling at ' + str(round(sellAt, 2)))
                self.coinState[c].purchasedPrice = price
                self.coinState[c].numHeld = shares
                self.coinState[c].timeBought = str(datetime.datetime.now())
                self.coinState[c].numBought = shares
                self.boughtIn = True

        return

    def checkBuyCondition(self, c):

        if self.buysLockedCounter > 0:
            print(str(self.coinList[c]) + ': Buys locked due to break in price update stream')
            return False

        # look at values in last row only
        price = self.data.iloc[-1][self.coinList[c]]
        movingAverage = self.data.iloc[-1][str(self.coinList[c]) + '_SMA']
        RSI = self.data.iloc[-1][str(self.coinList[c]) + '_RSI']
        bolB = self.data.iloc[-1][str(self.coinList[c]) + '_bolB']

        if math.isnan(movingAverage) == False and math.isnan(RSI) == False and math.isnan(bolB) == False:
            # this is the heart of how the bot decides to buy a position. Modify this to fit your own trading strategy.
            # if (price < bolB) and (RSI <= 30):
            if RSI <= 30:
                print('Conditions met to buy! ' + str(self.coinList[c]) + ' fell out of bottom bollinger, and RSI is below 15... attempting to buy...')
                return True

        return False

    def checkSellCondition(self, c):

        # look at values in last row only
        price = self.data.iloc[-1][self.coinList[c]]
        # check the RSI of coin[c]
        RSI = self.data.iloc[-1][str(self.coinList[c]) + '_RSI']
        print(str(self.coinList[c]) + ' RSI: ' + str(round(RSI, 0)))
        # this is the heart of how the bot decides to sell a position. Modify this to fit your own trading strategy.
        if math.isnan(RSI) == False and self.coinState[c].purchasedPrice > 0.0:
            if price > self.coinState[c].purchasedPrice + (self.coinState[c].purchasedPrice * self.sellAboveBuyPrice) and self.coinState[c].numHeld > 0.0:
                return True

        return False

    def checkConsecutive(self, now):

        print('\nChecking for consecutive times..')

        # check for break between now and last sample
        lastDateStamp = self.data.iloc[-1]['exec_time']
        timeDelta = now - lastDateStamp
        minutes = (timeDelta.seconds/60)
        if minutes > self.minutesBetweenUpdates:
            print('It has been too long since last price point gathered, holding buys.\n')
            return False

        if self.data.shape[0] <= 1:
            return True

        # check for break in sequence of samples to minimum consecutive sample number
        position = len(self.data) - 1
        for x in range(0, self.minConsecutiveSamples):
            t1 = self.data.iloc[position - x]['exec_time']
            t2 = self.data.iloc[position - (x + 1)]['exec_time']
            timeDelta = t1 - t2
            minutes = (timeDelta.seconds/60)

            if minutes > self.minutesBetweenUpdates:
                print('Interruption found in price data, holding buys until ' + str(self.minutesBetweenUpdates) + ' > ' + str(minutes))
                return False

        return True

    def updateDataframe(self, now):
        # we check this each time, so we don't need to lock for more than two cycles. It will set back to two if it fails on the next pass.
        if self.data.shape[0] > 0:
            if self.checkConsecutive(now) == False:
                self.buysLockedCounter = 2

        # tick down towards being able to buy again, if not there already.
        if self.buysLockedCounter > 0:
            self.buysLockedCounter = self.buysLockedCounter - 1

        rowdata = {}

        currentPrices = self.getPrices()
        if len(currentPrices) == 0:
            print('Exception received getting prices, not adding data, locking buys')
            self.buysLockedCounter = 2
            self.pricesGood = False
            return self.data

        self.pricesGood = True
        rowdata.update({'exec_time': now})

        for c in self.coinList:
            rowdata.update({c: currentPrices[c]})

        self.data = self.data.append(rowdata, ignore_index=True)


        # generate technical alaysis values (there are a TON more of these avialable in the TA-Lib library, see https://mrjbq7.github.io/ta-lib/funcs.html) These values are what the checkSellCondition and checkBuyCondition function will use to determine if it's time to buy and sell, so choose wisely!
        for c in self.coinList:
            self.data[c + '_SMA'] = talib.SMA(self.data[c].values, timeperiod=self.movingAverageWindows)
            self.data[c + '_RSI'] = talib.RSI(self.data[c].values, timeperiod=self.rsiWindow)
            upper, middle, bottom = talib.BBANDS(self.data[c].values, timeperiod=self.movingAverageWindows, nbdevup=2, nbdevdn=2, matype=0)
            self.data[c + '_bolU'] = upper
            self.data[c + '_bolM'] = middle
            self.data[c + '_bolB'] = bottom

        print(self.data.tail(31))

        return self.data

    def loadDataframe(self):

        if path.exists('data/dataframe.pickle'):

            print('Restoring state...')

            self.data = pd.read_pickle('data/dataframe.pickle')
            print(self.data.tail(31))

        else:

            column_names = ['exec_time']

            for c in self.coinList:
                column_names.append(c)

            self.data = pd.DataFrame(columns=column_names)

        return self.data

    def getIncrements(self):

        self.minIncrements = {}
        self.minPriceIncrements = {}

        for c in range(0, len(self.coinList)):
            code = self.coinList[c]

            try:
                result = self.client.get_symbol_info(symbol=code)
                for fil in result['filters']:
                    if fil['filterType']=='LOT_SIZE':
                        inc = fil['stepSize']
                    if fil['filterType']=='PRICE_FILTER':
                        p_inc = fil['tickSize']
            except:
                print('Failed to get increments from Binance. Are you connected to the internet? Exiting.')
                exit()

            self.minIncrements.update({code: float(inc)})
            self.minPriceIncrements.update({code: float(p_inc)})

    def roundDown(self, x, a):
        # rounds down x to the nearest multiple of a
        return math.floor(x/a) * a

    def printState(self):

        print('Bought In: ' + str(self.boughtIn) + '\n')

        for c in self.coinState:
            if c.numHeld > 0.0:
                price = round(self.data.iloc[-1][c.name], 2)
                totalHeld = self.getHoldings(c.name)
                currentValue = price * totalHeld

                print('Coin: ' + str(c.name))
                print('Held: ' + str(totalHeld))
                print('Amount bought: ' + str(c.numBought))
                print('Time bought: ' + str(c.timeBought))
                print('Order ID: ' + str(c.lastBuyOrderID))
                print('Bought at: $' + str(c.purchasedPrice) + ' per coin for a total of $' + str(round(c.numBought * c.purchasedPrice, 2)))
                print('Current price: $' + str(price) + ' Needs to hit at least $' + str(round(((c.purchasedPrice *  self.sellAboveBuyPrice) + c.purchasedPrice), 2)) + ' for position to be worth at least $' + str(round(c.numBought * c.purchasedPrice * self.sellAboveBuyPrice + (c.numBought * c.purchasedPrice), 2)))
                print('Current position value: $' + str(round(currentValue, 2)))
        print('\n')

    def cancelOrder(self, code, orderID):
        print('Swing and miss, cancelling order ' + orderID)
        try:
            cancelResult = self.client.cancel_order(symbol=code, orderId=orderID)
            print(str(cancelResult))
        except:
            print('Got exception canceling order, will try again.')
            return False
        return True

    def runBot(self):

        self.printState()

        while (True):

            now = datetime.datetime.now()

            #is it time to pull prices?
            if (now.minute in self.runMinute):
                self.data = self.updateDataframe(now)
                #check for swing/miss on each coin here
                if self.boughtIn == True:
                    for c in self.coinState:
                        if (c.timeBought != ''):
                            dt_timeBought = datetime.datetime.strptime(c.timeBought, '%Y-%m-%d %H:%M:%S.%f')
                            timeDiffBuyOrder = now - dt_timeBought
                            coinHeld = self.getHoldings(c.name)
                            if coinHeld == -1:
                                print('Got exception trying to get holdings while checking for swing/miss, cancelling.')
                                return

                            if (timeDiffBuyOrder.total_seconds() > (60) and coinHeld == 0.0):
                                cancelled = self.cancelOrder(code=c.name, orderID=c.lastBuyOrderID)
                                if cancelled == True:
                                    c.purchasedPrice = 0.0
                                    c.numHeld = 0.0
                                    c.numBought = 0.0
                                    c.lastBuyOrderID = ''
                                    c.timeBought = ''
                                    self.boughtIn = False

                for c in range(0, len(self.coinList)):

                    if self.pricesGood and self.checkBuyCondition(c):
                        price = self.data.iloc[-1][self.coinList[c]]
                        self.buy(c, price)

                    if self.pricesGood and self.checkSellCondition(c):
                        price = self.data.iloc[-1][self.coinList[c]]
                        self.sell(c, price)

                self.printState()
                self.saveState()
                time.sleep(59.9)

        time.sleep(30)

def main():
    m = moneyBot()
    m.runBot()


if __name__ == '__main__':
    main()
