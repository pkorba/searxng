# SearXNG Bot

A maubot plugin for Matrix messaging that performs a web search on user's behalf using SearXNG and responds with the best matching result. It requires an access to SearXNG instance that exposes its JSON API. SearXNG is a free internet metasearch engine which aggregates results from up to 248 [search services](https://docs.searxng.org/user/configured_engines.html). This plugin supports [!bang syntax](https://docs.searxng.org/user/search-syntax.html#search-syntax) (except external bangs and automatic redirect) so it reduces the need for service specific plugins. 

![bot_searxng](https://github.com/user-attachments/assets/ddb5d7fe-10ae-4c68-bf8b-cab86ad7b955)


## Usage
Type the query you'd like to pass to the search engine.
```
[p]sx query
[p]searxng query
```

## Configuration

The available options are:
* `url` - public URL address of SearXNG instance.
* `port` - port number for `url`
* `language` - default search language. Available options are listed [here](https://github.com/searxng/searxng/blob/master/searx/sxng_locales.py#L12). Defaults to `all`.
* `safesearch` - available options are `on`, `off`, and `moderate` (default). Controls the safe search filter. Keep in mind that some engines may not support that feature. See if an engine supports safe search in the preferences page of a SearXNG instance.

## Notes

- This bot requires SearXNG instance to expose public JSON API. By default, this is disabled in instance's settings. You can change that by adding `json` to `formats` in `search` section of the settings (settings.yml):
```yaml
  # remove format to deny access, use lower case.
  # formats: [html, csv, json, rss]
  formats:
    - html
    - json  # <-- add this line
```

## Disclaimer

This plugin is not affiliated with SearXNG. The official SearXNG website can be found at https://docs.searxng.org/.
