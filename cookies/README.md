# Facebook Cookies for Authentication

Facebook Marketplace requires login. To use the scraper, export your cookies:

## Steps

1. **Install a cookie export extension** in your browser:
   - Chrome: [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg) or [Cookie-Editor](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
   - Firefox: [Cookie-Editor](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/)

2. **Log into Facebook** in your browser

3. **Export cookies**:
   - Click the cookie extension icon
   - Click "Export" (choose JSON format)
   - Save as `facebook_cookies.json` in this directory

4. **Restart the API container**:
   ```bash
   docker compose restart api
   ```

## Important Cookies

The most important cookies for Facebook auth are:
- `c_user` - Your user ID
- `xs` - Session token
- `datr` - Browser identifier

## Security Warning

- **Never commit** `facebook_cookies.json` to git (it's in .gitignore)
- These cookies give full access to your Facebook account
- Regenerate if you suspect they've been compromised (log out of Facebook)
