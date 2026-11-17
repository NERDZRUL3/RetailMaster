# Development image: pinned official ERPNext image + the retail_management app.
# Build context is the repository root.
#
# Production does not use Docker; see docs/deploy-lxc.md.
ARG ERPNEXT_VERSION=v16.55.0
FROM frappe/erpnext:${ERPNEXT_VERSION}

# Tesseract reads scanned delivery notes (api/delivery_notes.py).
USER root
RUN apt-get update \
	&& DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
		tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra tesseract-ocr-ara \
	&& rm -rf /var/lib/apt/lists/*
USER frappe

COPY --chown=frappe:frappe apps/retail_management /home/frappe/frappe-bench/apps/retail_management

RUN cd /home/frappe/frappe-bench \
	&& ( ./env/bin/python -m pip install --no-cache-dir -e apps/retail_management \
		|| uv pip install --python ./env/bin/python -e apps/retail_management ) \
	# Serve the app's public folder (built interface) at /assets/retail_management,
	# the same way the image links frappe and erpnext.
	&& ln -s /home/frappe/frappe-bench/apps/retail_management/retail_management/public \
		/home/frappe/frappe-bench/assets/retail_management
