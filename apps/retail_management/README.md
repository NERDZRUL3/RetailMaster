# Retail Management

Custom Frappe app for Retail Manager. Requires ERPNext 16.

It extends ERPNext through supported extension points only (custom DocTypes,
hooks, whitelisted APIs). It does not modify Frappe or ERPNext core.

## Install on a bench

```bash
bench get-app /path/to/apps/retail_management
bench --site <site> install-app retail_management
```

## Tests

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app retail_management
```
