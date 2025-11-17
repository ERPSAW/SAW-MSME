# Copyright (c) 2025, SAW India and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, add_days

def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_columns(filters):
	columns = [
		{"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 200},
		{"label": "Supplier Name", "fieldname": "supplier_name", "fieldtype": "Data", "width": 250},
		{"label": "MSME Reg No", "fieldname": "msme_registration_no", "fieldtype": "Data", "width": 200},
		{"label": "MSME Type", "fieldname": "msme_type", "fieldtype": "Data", "width": 150},
		{"label": "MSME Contract Done", "fieldname": "msme_contract_done", "fieldtype": "Data", "width": 120},
	]

	if filters.get("detail_summary"):
		columns += [
			{"label": "Purchase Invoice", "fieldname": "purchase_invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 250},
			{"label": "Purchase Invoice Date", "fieldname": "purchase_invoice_date", "fieldtype": "Date", "width": 150},
			{"label": "Supplier Invoice Date", "fieldname": "supplier_invoice_date", "fieldtype": "Date", "width": 150},
		]

	columns += [
		{"label": "Paid Amount After 45 Days", "fieldname": "paid_after_45", "fieldtype": "Currency", "width": 180},
		{"label": "Outstanding for 45 Days or less", "fieldname": "outstanding_45_less", "fieldtype": "Currency", "width": 180},
		{"label": "Outstanding for more than 45 Days", "fieldname": "outstanding_45_more", "fieldtype": "Currency", "width": 180},
	]

	return columns


def get_data(filters):
	data = []
	raw_data_dict = {}
	conditions = ""

	if filters.get("ageing_based_on") == "Posting Date":
		conditions += "pi.posting_date between %(from_date)s and %(to_date)s"
	elif filters.get("ageing_based_on") == "Supplier Invoice Date":
		conditions += "pi.bill_date between %(from_date)s and %(to_date)s AND pi.bill_date IS NOT NULL"
	else:
		return data

	if filters.get("supplier"):
		conditions += " and pi.supplier = %(supplier)s"
	if filters.get("supplier_group"):
		conditions += " and s.supplier_group = %(supplier_group)s"
	if filters.get("custom_msme_type"):
		conditions += " and s.custom_msme_type = %(custom_msme_type)s"
	if filters.get("custom_contract_done"):
		conditions += " and s.custom_contract_done = %(custom_contract_done)s"

	invoices = frappe.db.sql("""
		SELECT
			pi.name,
			pi.supplier,
			pi.supplier_name,
			pi.grand_total,
			pi.posting_date,
			pi.bill_date,
			s.custom_msme_registration_no,
			s.custom_msme_type,
			s.custom_contract_done
		FROM `tabPurchase Invoice` pi
		LEFT JOIN `tabSupplier` s ON s.name = pi.supplier
		WHERE {0}
		AND pi.docstatus = 1
	""".format(conditions), filters, as_dict=True)

	for inv in invoices:
		paid_after_45 = 0
		outstanding_45_less = 0
		outstanding_45_more = 0

		due_date_45 = add_days(inv.posting_date, 45) if filters.get("ageing_based_on") == "Posting Date" else add_days(inv.bill_date, 45)

		# Get all payments made against this invoice
		payments = frappe.db.sql("""
			SELECT pe.posting_date, per.allocated_amount
			FROM `tabPayment Entry Reference` as per
			LEFT JOIN `tabPayment Entry` as pe ON pe.name = per.parent
			WHERE per.reference_name = %s
				AND pe.docstatus = 1
				AND per.reference_doctype = 'Purchase Invoice'
				AND per.allocated_amount > 0
		""", (inv.name,), as_dict=True)

		total_paid = 0
		for p in payments:
			total_paid += p.allocated_amount

			# Check if payment is after 45 days
			if getdate(p.posting_date) > getdate(due_date_45):
				paid_after_45 += p.allocated_amount

		gl_payments = frappe.db.sql("""
			SELECT jea.debit_in_account_currency, je.posting_date
			FROM `tabJournal Entry Account` as jea
			LEFT JOIN `tabJournal Entry` as je ON je.name = jea.parent
			WHERE je.docstatus = 1
			AND jea.debit_in_account_currency > 0
			AND jea.reference_type = 'Purchase Invoice'
			AND jea.reference_name = %s
		""", (inv.name,), as_dict=True)

		for p in gl_payments:
			total_paid += p.debit_in_account_currency

			# Check if payment is after 45 days
			if getdate(p.posting_date) > getdate(due_date_45):
				paid_after_45 += p.debit_in_account_currency

		outstanding = inv.grand_total - total_paid

		# Categorize outstanding
		if outstanding > 0:
			if getdate(frappe.utils.nowdate()) <= getdate(due_date_45):
				outstanding_45_less = outstanding
			else:
				outstanding_45_more = outstanding

		if not filters.get("detail_summary"):
			if inv.supplier not in raw_data_dict:
				raw_data_dict[inv.supplier] = {
					"supplier": inv.supplier,
					"supplier_name": inv.supplier_name,
					"msme_registration_no": inv.custom_msme_registration_no,
					"msme_type": inv.custom_msme_type,
					"msme_contract_done": inv.custom_contract_done,
					"paid_after_45": paid_after_45,
					"outstanding_45_less": outstanding_45_less,
					"outstanding_45_more": outstanding_45_more
				}
			else:
				raw_data_dict[inv.supplier]["paid_after_45"] += paid_after_45
				raw_data_dict[inv.supplier]["outstanding_45_less"] += outstanding_45_less
				raw_data_dict[inv.supplier]["outstanding_45_more"] += outstanding_45_more
		else:
			# # Append to report
			data.append({
				"supplier": inv.supplier,
				"supplier_name": inv.supplier_name,
				"purchase_invoice": inv.name,
				"purchase_invoice_date": inv.posting_date,
				"supplier_invoice_date": inv.bill_date,
				"msme_registration_no": inv.custom_msme_registration_no,
				"msme_type": inv.custom_msme_type,
				"msme_contract_done": inv.custom_contract_done,
				"paid_after_45": paid_after_45,
				"outstanding_45_less": outstanding_45_less,
				"outstanding_45_more": outstanding_45_more,
			})

	if not filters.get("detail_summary"):
		for item, raw in raw_data_dict.items():
			data.append(raw)

	return data
