# Degree Cell Management System

Standalone Django project for physical degree application processing.

## Included workflow

- Admin, Desk Officer, Printing Officer roles
- Institute/department master data
- Program master data with program level
- Bank master data
- Fee structure based on program level, application type, and timing
- Document checklist gate before application entry
- Application entry from physical form
- Fee validation at entry using declared result date
- Tracking number format: `DC-YY-0001`, yearly reset
- POS-style receipt print
- Duplicate warning by CNIC or registration number, no hard block
- Verification stage with result declaration date confirmation
- Fee recalculation only if verified date differs from entered date
- Status flow:
  - Received
  - Verified
  - Sent for Printing
  - Received for Print
  - Printed
  - Submitted for Approval
  - Ready for Collection
  - Delivered
  - Cancelled
- Printing officer enters degree serial number and book number
- VC file creation from printed degrees
- VC file submission and return bulk-update applications
- Delivery details, including courier information
- Excel export
- Audit/status log

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## PostgreSQL

Edit `.env`:

```env
DB_ENGINE=postgres
DB_NAME=degree_cell
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

## First required setup in Admin

1. Create users and assign roles in User Profiles.
2. Add Banks.
3. Add Institutes.
4. Add Programs.
5. Add Fee Structures for every combination:
   - program level
   - Normal/Urgent
   - Before Time/After Time

## Notes

Before Time means result declaration date is within 60 days from current date.
After Time means result declaration date is older than 60 days.
