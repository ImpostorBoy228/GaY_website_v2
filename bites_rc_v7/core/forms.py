from django import forms
from .models import Video, Comment, Channel, UserProfile, Ad
from django.core.exceptions import ValidationError
from youtube_api.services import YouTubeService

class VideoUploadForm(forms.ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите название видео'
        })
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Введите описание видео',
            'rows': 4
        }),
        required=False
    )
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'video/*'
        })
    )
    thumbnail = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        required=False
    )
    # Добавляем поле для тегов
    tags = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите теги через запятую'
        }),
        required=False,
        help_text='Разделяйте теги запятыми, например: музыка, рок, концерт'
    )
    auto_generate_tags = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label='Автоматически генерировать теги',
        help_text='Теги будут сгенерированы на основе названия и описания видео'
    )


    class Meta:
        model = Video
        fields = ['title', 'description', 'file', 'thumbnail', 'channel']

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if not file.content_type.startswith('video/'):
                raise ValidationError('Пожалуйста, загрузите видео файл')
            if file.size > 500 * 1024 * 1024:  # 500MB
                raise ValidationError('Размер файла не должен превышать 500MB')
        return file

    def clean_thumbnail(self):
        thumbnail = self.cleaned_data.get('thumbnail')
        if thumbnail:
            if not thumbnail.content_type.startswith('image/'):
                raise ValidationError('Пожалуйста, загрузите изображение для превью')
            if thumbnail.size > 5 * 1024 * 1024:  # 5MB
                raise ValidationError('Размер превью не должен превышать 5MB')
        return thumbnail

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content', 'sentiment']

class UserProfileForm(forms.ModelForm):
    avatar = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        required=False
    )
    
    bio = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Расскажите о себе',
            'rows': 4
        }),
        required=False
    )
    
    class Meta:
        model = UserProfile
        fields = ['avatar', 'bio']

class ChannelForm(forms.ModelForm):
    class Meta:
        model = Channel
        fields = ['name', 'description', 'avatar', 'banner']
 


# Added AdForm for advertisement management
class AdForm(forms.ModelForm):
    class Meta:
        model = Ad
        fields = ['title', 'video_file', 'thumbnail', 'frequency', 'active']


class YouTubeImportSettingsForm(forms.Form):
    import_mode = forms.ChoiceField(
        choices=[
            ('single', 'Один URL'),
            ('multiple', 'Несколько URL'),
            ('search', 'Поиск видео'),
            ('channel', 'По каналу')
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Режим импорта'
    )
    single_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://www.youtube.com/watch?v=...'
        }),
        label='Ссылка на видео'
    )
    multiple_urls = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Одна ссылка в строке',
            'rows': 3
        }),
        label='Несколько ссылок'
    )
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите поисковый запрос'
        }),
        label='Поисковый запрос'
    )
    channel_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://www.youtube.com/channel/...'
        }),
        label='Ссылка на канал'
    )
    use_filters = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label='Применить фильтры'
    )
    min_views = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0'
        }),
        label='Минимум просмотров'
    )
    max_views = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0'
        }),
        label='Максимум просмотров'
    )
    min_duration = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0'
        }),
        label='Минимальная длительность (сек)'
    )
    max_duration = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0'
        }),
        label='Максимальная длительность (сек)'
    )
    max_count = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '10'
        }),
        label='Максимальное количество видео',
        initial=10
    )