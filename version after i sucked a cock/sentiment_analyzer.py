import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers.utils.generic")

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
import torch
import os

class SentimentAnalyzer:
    def __init__(self, model_path="./rubert-tiny2-russian-sentiment", model_name="seara/rubert-tiny2-russian-sentiment"):
        model_path = os.path.abspath(model_path)
        try:
            if not os.path.exists(model_path):
                print(f"Директория модели {model_path} не найдена. Загружаем модель {model_name}...")
                os.makedirs(model_path, exist_ok=True)
                model = AutoModelForSequenceClassification.from_pretrained(model_name)
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model.save_pretrained(model_path)
                tokenizer.save_pretrained(model_path)
                print(f"Модель успешно сохранена в {model_path}")
            else:
                print(f"Загружаем модель из {model_path}")
            model = AutoModelForSequenceClassification.from_pretrained(model_path)
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.classifier = pipeline(
                "sentiment-analysis",
                model=model,
                tokenizer=tokenizer,
                top_k=None,
                device=0 if torch.cuda.is_available() else -1
            )
        except Exception as e:
            raise RuntimeError(f"Не удалось загрузить модель из {model_path}: {str(e)}")

    def analyze(self, text):
        try:
            text = text[:512]
            with torch.no_grad():
                results = self.classifier(text)[0]
            scores = {result['label'].lower(): result['score'] for result in results}
            positive_score = scores.get('positive', 0.0)
            neutral_score = scores.get('neutral', 0.0)
            negative_score = scores.get('negative', 0.0)
            max_score = max(positive_score, neutral_score, negative_score)
            if max_score == positive_score:
                return 1.0
            elif max_score == neutral_score:
                return 0.5
            else:
                return 0.0
        except Exception as e:
            print(f"Ошибка при анализе текста: {str(e)}")
            return 0.5