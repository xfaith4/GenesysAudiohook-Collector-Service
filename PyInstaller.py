# From your project folder
python -m pip install --upgrade pyinstaller
# Bundle, including aiohttp + your optional topics.json as data
pyinstaller `
  --onefile `
  --name GenesysAudioHookCollector `
  --add-data "topics.json;." `
  collector.py
