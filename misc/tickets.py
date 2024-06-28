from dataclasses import dataclass
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black
import qrcode


@dataclass
class EventInfo:
    name: str
    date: str
    location: str


@dataclass
class TicketInfo:
    event: EventInfo
    attendee: str
    seat: str
    secret: str

    def to_pdf(self, filename: str):
        # PDF settings
        width, height = 5.5 * inch, 2.125 * inch
        c = canvas.Canvas(filename, pagesize=(width, height))

        # Background color
        c.setFillColor(Color(0.95, 0.95, 0.95, alpha=1))  # Light grey background
        c.rect(0, 0, width, height, fill=1)

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.secret)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        img = ImageReader(qr_img.get_image())

        # Draw QR code on PDF
        c.drawImage(
            img,
            width - 1.75 * inch,
            0.25 * inch,
            1.5 * inch,
            1.5 * inch,
        )

        # Draw text on PDF
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(black)
        c.drawString(0.25 * inch, height - 0.5 * inch, self.event.name)

        c.setFont("Helvetica", 12)
        c.drawString(0.25 * inch, height - 0.75 * inch, self.event.date)
        c.drawString(0.25 * inch, height - 1.0 * inch, self.event.location)

        c.setFont("Helvetica-Bold", 12)
        c.drawString(0.25 * inch, height - 1.5 * inch, f"Attendee: {self.attendee}")

        c.setFont("Helvetica", 12)
        c.drawString(0.25 * inch, height - 1.75 * inch, f"Seat: {self.seat}")

        # Optional: Add a logo or other images
        # c.drawImage("path/to/logo.png", x, y, width, height)

        # Save PDF
        c.showPage()
        c.save()

    def to_pdf2(self, filename: str):
        # PDF settings
        width, height = 5.5 * inch, 2.125 * inch
        c = canvas.Canvas(filename, pagesize=(width, height))

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.secret)
        qr.make(fit=True)
        qr_img = qr.make_image(fill="black", back_color="white")
        img = ImageReader(qr_img.get_image())

        # Draw QR code on PDF
        c.drawImage(
            img,
            width - 1.5 * inch,
            0.25 * inch,
            1.25 * inch,
            1.25 * inch,
        )

        # Draw text on PDF
        c.setFont("Helvetica-Bold", 12)
        c.drawString(0.25 * inch, height - 0.5 * inch, self.event.name)
        c.setFont("Helvetica", 10)
        c.drawString(0.25 * inch, height - 0.75 * inch, self.event.date)
        c.drawString(0.25 * inch, height - 1.0 * inch, self.event.location)
        c.drawString(0.25 * inch, height - 1.5 * inch, f"Attendee: {self.attendee}")
        c.drawString(0.25 * inch, height - 1.75 * inch, f"Seat: {self.seat}")

        # Save PDF
        c.showPage()
        c.save()


if __name__ == "__main__":
    # Create an instance of EventInfo and TicketInfo
    event = EventInfo(name="Concert", date="2024-07-20", location="Stadium XYZ")
    ticket = TicketInfo(event=event, attendee="John Doe", seat="A12", secret="12345ABC")

    # Generate the PDF
    ticket.to_pdf("ticket.pdf")
