import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier
from loguru import logger
from typing import Tuple, Dict
import joblib
import os

class HybridPredictionEngine:
    def __init__(self, lstm_weight: float = 0.4, xgb_weight: float = 0.6):
        self.lstm_weight = lstm_weight
        self.xgb_weight = xgb_weight
        self.xgb_model = None
        self.scaler = MinMaxScaler()
        
    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract technical indicators as features"""
        features = df.copy()
        
        # Moving averages
        features['sma_20'] = features['close'].rolling(20).mean()
        features['sma_50'] = features['close'].rolling(50).mean()
        
        # RSI
        delta = features['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        features['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_12 = features['close'].ewm(span=12).mean()
        ema_26 = features['close'].ewm(span=26).mean()
        features['macd'] = ema_12 - ema_26
        
        # Bollinger Bands
        features['bb_middle'] = features['close'].rolling(20).mean()
        bb_std = features['close'].rolling(20).std()
        features['bb_upper'] = features['bb_middle'] + (bb_std * 2)
        features['bb_lower'] = features['bb_middle'] - (bb_std * 2)
        
        # Volume indicators
        features['volume_sma'] = features['volume'].rolling(20).mean()
        
        return features.dropna()
    
    def xgboost_predict(self, features: pd.DataFrame, lookback: int = 60) -> np.ndarray:
        """XGBoost predictions"""
        feature_cols = ['sma_20', 'sma_50', 'rsi', 'macd', 'bb_upper', 'bb_lower', 'volume_sma']
        
        if len(features) < lookback:
            return np.array([0.5] * len(features))
        
        X = features[feature_cols].values
        
        # Create labels (1 if next day close > current close, 0 otherwise)
        y = (features['close'].shift(-1) > features['close']).astype(int).values
        
        if self.xgb_model is None:
            self.xgb_model = XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            )
            self.xgb_model.fit(X[:-1], y[:-1])
        
        predictions = self.xgb_model.predict_proba(X)[:, 1]
        return predictions
    
    def predict(self, df: pd.DataFrame) -> Dict:
        """Generate hybrid predictions"""
        features = self.extract_features(df)
        
        # XGBoost predictions
        xgb_probs = self.xgboost_predict(features)
        
        # Combine signals
        final_signal = xgb_probs[-1]
        
        return {
            "up_probability": final_signal,
            "down_probability": 1 - final_signal,
            "signal": "BUY" if final_signal > 0.65 else "SELL" if final_signal < 0.35 else "HOLD",
            "confidence": max(final_signal, 1 - final_signal)
        }