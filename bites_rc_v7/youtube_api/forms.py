from django import forms


class VideoImportForm(forms.Form):
    video_url = forms.URLField(
        label='YouTube Video URL',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.youtube.com/watch?v=...'})
    )


class ChannelImportForm(forms.Form):
    channel_url = forms.URLField(
        label='YouTube Channel URL',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.youtube.com/channel/...'})
    )


class VideoSearchForm(forms.Form):
    query = forms.CharField(
        label='Search Query',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search videos...'})
    )
    min_views = forms.IntegerField(required=False)
    min_likes = forms.IntegerField(required=False)
    upload_date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    upload_date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    sort_by = forms.ChoiceField(
        required=False,
        choices=[
            ('-upload_date', 'Newest First'),
            ('upload_date', 'Oldest First'),
            ('-views', 'Most Viewed'),
            ('views', 'Least Viewed'),
            ('-absolute_rating', 'Highest Rating'),
            ('absolute_rating', 'Lowest Rating'),
            ('antitop', 'Antitop Rating'),
        ],
        initial='-upload_date'
    )