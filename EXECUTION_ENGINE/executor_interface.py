from abc import ABC, abstractmethod

class OrderExecutor(ABC):
    """
    Abstract Base Class (Adapter Interface) for Broker Executions.
    Any new broker (IBKR, Alpaca, etc.) must implement these methods.
    """

    @abstractmethod
    def connect(self):
        """Authenticates with the broker API."""
        pass

    @abstractmethod
    def get_account_balance(self):
        """Returns available buying power/cash."""
        pass

    @abstractmethod
    def get_current_price(self, ticker):
        """Returns real-time price for a ticker."""
        pass

    @abstractmethod
    def place_entry_with_bracket(self, ticker, dollar_amount, stop_loss_pct, moonshot_pct):
        """
        Places an entry order immediately followed by protection orders.
        Returns a dict with trade details or None on failure.
        """
        pass

    @abstractmethod
    def place_market_sell(self, ticker, quantity):
        """Executes an immediate market sell for the specified quantity."""
        pass

    @abstractmethod
    def cancel_all_orders(self, ticker):
        """Cancels all open orders (Limit/Stop) for a specific ticker."""
        pass
