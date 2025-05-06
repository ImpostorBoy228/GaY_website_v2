def analyze_sentiment(text):
    """
    Analyze the sentiment of a given text using a simple rule-based approach.
    Returns:
        1.0 for positive sentiment
        0.0 for negative sentiment
        0.5 for neutral sentiment
    """
    # Convert text to lowercase for case-insensitive matching
    text = text.lower()
    
    # Define positive and negative word lists
    positive_words = {
        'хорошо', 'отлично', 'супер', 'класс', 'круто', 'люблю', 'нравится',
        'замечательно', 'прекрасно', 'восхитительно', 'потрясающе', 'здорово',
        'полезно', 'интересно', 'увлекательно', 'познавательно', 'спасибо',
        'благодарю', 'рекомендую', 'советую', 'поддерживаю', 'согласен',
        'верно', 'правильно', 'точно', 'именно', 'да', 'да', 'да'
    }
    
    negative_words = {
        'плохо', 'ужасно', 'отстой', 'неудачно', 'неудачный', 'неудача',
        'неправильно', 'ошибка', 'ошибочно', 'неверно', 'неверный',
        'негативно', 'отрицательно', 'негативный', 'отрицательный',
        'неудобно', 'сложно', 'трудно', 'тяжело', 'проблема', 'проблемный',
        'недостаток', 'недостаточно', 'мало', 'мало', 'мало'
    }
    
    # Count positive and negative words
    positive_count = sum(1 for word in text.split() if word in positive_words)
    negative_count = sum(1 for word in text.split() if word in negative_words)
    
    # Calculate sentiment score
    total = positive_count + negative_count
    if total == 0:
        return 0.5  # Neutral if no sentiment words found
    
    sentiment_score = positive_count / total
    
    # Return sentiment value
    if sentiment_score > 0.6:
        return 1.0  # Positive
    elif sentiment_score < 0.4:
        return 0.0  # Negative
    else:
        return 0.5  # Neutral 