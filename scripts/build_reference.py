"""Build data/reference.json: dated facts copied from official documents, each with its source. Run: python scripts/build_reference.py
Holiday rows are transcribed by hand from the two documents named in SOURCES (the PDFs are scans, so there is no parser). To add a year: read the
new DoPT office memorandum, add its rows below, run this script, run tests/test_refstore.py."""
import json, os

SOURCES = {
    "dopt2026": {"name": "Government of India holiday list 2026 (DoPT O.M. F.No.12/2/2023-JCA dated 03.07.2025, as circulated by Survey of India)",
                 "url": "https://surveyofindia.gov.in/documents/circulars/document-38128-Delhi%20GD-RO-22-01-2026.pdf", "read_on": "2026-11-18"},
    "dopt2026_bakrid": {"name": "Change of date of the Id-u-Zuha (Bakrid) holiday to 28 May 2026 for central government offices in Delhi (circulated by ICMR, 25.05.2026)",
                        "url": "https://www.icmr.gov.in/icmrobject/uploads/Circular/1779704410_changeofdateofholidayonaccountofid-u-zuha.pdf", "read_on": "2026-11-18"},
    "dopt2027": {"name": "Government of India holiday list 2027 (DoPT O.M. No.12/2/2023-JCA dated 16.07.2026, as circulated by the Department of Posts)",
                 "url": "https://utilities.cept.gov.in/dop/pdfbind.ashx?id=15435", "read_on": "2026-11-18"},
}
G, R = "gazetted", "restricted"      # gazetted = closed holiday for central government offices in Delhi; restricted = optional holiday
# (id, name, kind, date in 2026, date in 2027). None = not in that year's list.
ROWS = [
    ("republic_day", "Republic Day", G, "01-26", "01-26"),
    ("holi", "Holi", G, "03-04", "03-23"),
    ("id_ul_fitr", "Id-ul-Fitr (Eid)", G, "03-21", "03-10"),
    ("ram_navami", "Ram Navami", G, "03-26", "04-15"),
    ("mahavir_jayanti", "Mahavir Jayanti", G, "03-31", "04-19"),
    ("good_friday", "Good Friday", G, "04-03", "03-26"),
    ("buddha_purnima", "Buddha Purnima", G, "05-01", "05-20"),
    ("bakrid", "Id-ul-Zuha (Bakrid)", G, "05-28", "05-17"),
    ("muharram", "Muharram", G, "06-26", "06-16"),
    ("independence_day", "Independence Day", G, "08-15", "08-15"),
    ("id_e_milad", "Milad-un-Nabi (Id-e-Milad)", G, "08-26", "08-15"),
    ("janmashtami", "Janmashtami", G, "09-04", "08-25"),
    ("gandhi_jayanti", "Mahatma Gandhi's Birthday (Gandhi Jayanti)", G, "10-02", "10-02"),
    ("dussehra", "Dussehra (Vijaya Dashami)", G, "10-20", "10-09"),
    ("diwali", "Diwali (Deepavali)", G, "11-08", "10-29"),
    ("guru_nanak_jayanti", "Guru Nanak's Birthday", G, "11-24", "11-14"),
    ("christmas", "Christmas Day", G, "12-25", "12-25"),
    ("new_year", "New Year's Day", R, "01-01", "01-01"),
    ("makar_sankranti", "Makar Sankranti", R, "01-14", "01-14"),
    ("pongal", "Pongal", R, "01-14", "01-15"),
    ("basant_panchami", "Basant Panchami (Sri Panchami)", R, "01-23", "02-11"),
    ("guru_ravidas_jayanti", "Guru Ravidas's Birthday", R, "02-01", "02-20"),
    ("dayanand_jayanti", "Swami Dayananda Saraswati Jayanti", R, "02-12", "03-02"),
    ("maha_shivratri", "Maha Shivratri", R, "02-15", "03-06"),
    ("shivaji_jayanti", "Shivaji Jayanti", R, "02-19", "02-19"),
    ("holika_dahan", "Holika Dahan (Dolyatra)", R, "03-03", "03-22"),
    ("ugadi", "Ugadi / Gudi Padwa / Cheti Chand (Chaitra Sukladi)", R, "03-19", "04-07"),
    ("jamat_ul_vida", "Jamat-ul-Vida", R, "03-20", "03-05"),
    ("easter", "Easter Sunday", R, "04-05", "03-28"),
    ("vaisakhi", "Vaisakhi / Vishu / Tamil New Year's Day", R, "04-14", "04-14"),
    ("bohag_bihu", "Vaisakhadi (Bengal) / Bohag Bihu (Assam)", R, "04-15", "04-15"),
    ("tagore_jayanti", "Rabindranath Tagore's Birthday", R, "05-09", "05-09"),
    ("rath_yatra", "Rath Yatra", R, "07-16", "07-05"),
    ("parsi_new_year", "Parsi New Year's Day (Navroz)", R, "08-15", "08-15"),
    ("onam", "Onam (Thiru Onam)", R, "08-26", "09-12"),
    ("raksha_bandhan", "Raksha Bandhan", R, "08-28", "08-17"),
    ("ganesh_chaturthi", "Ganesh Chaturthi (Vinayaka Chaturthi)", R, "09-14", "09-04"),
    ("maha_ashtami", "Dussehra (Maha Ashtami)", R, "10-19", "10-07"),
    ("maha_navami", "Dussehra (Maha Navami)", R, "10-20", "10-08"),
    ("valmiki_jayanti", "Maharishi Valmiki's Birthday", R, "10-26", "10-15"),
    ("karva_chauth", "Karva Chauth", R, "10-29", "10-18"),
    ("naraka_chaturdasi", "Naraka Chaturdasi", R, "11-08", "10-28"),
    ("govardhan_puja", "Govardhan Puja", R, "11-09", "10-30"),
    ("bhai_duj", "Bhai Duj", R, "11-11", "10-31"),
    ("chhath", "Chhath Puja", R, "11-15", "11-04"),
    ("guru_teg_bahadur", "Guru Teg Bahadur's Martyrdom Day", R, "11-24", "11-24"),
    ("christmas_eve", "Christmas Eve", R, "12-24", "12-24"),
]
MOON = {"id_ul_fitr", "bakrid", "muharram", "id_e_milad"}     # the O.M. says these dates can change with the sighting of the Moon

def main():
    facts = []
    for fid, name, kind, d26, d27 in ROWS:
        for year, md, src in ((2026, d26, "dopt2026"), (2027, d27, "dopt2027")):
            if md:
                f = {"id": fid, "name": name, "kind": kind, "date": f"{year}-{md}", "source": src}
                if fid == "bakrid" and year == 2026:
                    f["source"], f["note"] = "dopt2026_bakrid", "Moved from 27 May to 28 May 2026 for offices in Delhi; other states could decide their own date."
                elif fid in MOON:
                    f["note"] = "This date can change with the sighting of the Moon."
                facts.append(f)
    out = os.path.join(os.path.dirname(__file__), "..", "data", "reference.json")
    json.dump({"sources": SOURCES, "holidays": facts}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("wrote", len(facts), "holiday facts")

if __name__ == "__main__":
    main()
