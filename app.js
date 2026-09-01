const roomRates = {
  Standard: 120,
  Deluxe: 180,
  Suite: 260,
};

const form = document.getElementById('booking-form');
const summaryCard = document.getElementById('booking-summary');
const bookingList = document.getElementById('booking-list');

const checkInInput = document.getElementById('checkIn');
const checkOutInput = document.getElementById('checkOut');

const bookings = [
  {
    guestName: 'Ava Patel',
    roomType: 'Deluxe',
    checkIn: '2026-08-10',
    checkOut: '2026-08-13',
    guestCount: 2,
  },
  {
    guestName: 'Noah Benson',
    roomType: 'Suite',
    checkOut: '2026-08-15',
    checkIn: '2026-08-12',
    guestCount: 3,
  },
];

function getNightCount(checkIn, checkOut) {
  const start = new Date(checkIn);
  const end = new Date(checkOut);
  const diff = end - start;
  return Math.max(1, Math.round(diff / (1000 * 60 * 60 * 24)));
}

function renderSummary() {
  const guestName = document.getElementById('guestName').value.trim();
  const roomType = document.getElementById('roomType').value;
  const checkIn = checkInInput.value;
  const checkOut = checkOutInput.value;
  const guestCount = Number(document.getElementById('guestCount').value);

  if (!guestName || !checkIn || !checkOut || !guestCount) {
    summaryCard.innerHTML = '<p>Select a stay to see the total price.</p>';
    return;
  }

  const nights = getNightCount(checkIn, checkOut);
  const rate = roomRates[roomType] || 0;
  const total = nights * rate + guestCount * 20;

  summaryCard.innerHTML = `
    <p><strong>${guestName}</strong> • ${roomType} room</p>
    <p>${checkIn} → ${checkOut}</p>
    <p>${nights} nights • ${guestCount} guests</p>
    <p><strong>Total estimate: $${total}</strong></p>
  `;
}

function renderBookings() {
  bookingList.innerHTML = '';

  bookings.forEach((booking) => {
    const li = document.createElement('li');
    const nights = getNightCount(booking.checkIn, booking.checkOut);
    const rate = roomRates[booking.roomType] || 0;
    const total = nights * rate;

    li.innerHTML = `
      <div>
        <strong>${booking.guestName}</strong><br />
        <small>${booking.roomType} • ${booking.guestCount} guests</small>
      </div>
      <div>
        <strong>$${total}</strong><br />
        <small>${booking.checkIn} → ${booking.checkOut}</small>
      </div>
    `;

    bookingList.appendChild(li);
  });
}

form.addEventListener('submit', (event) => {
  event.preventDefault();

  const booking = {
    guestName: document.getElementById('guestName').value.trim(),
    roomType: document.getElementById('roomType').value,
    checkIn: checkInInput.value,
    checkOut: checkOutInput.value,
    guestCount: Number(document.getElementById('guestCount').value),
  };

  if (!booking.guestName || !booking.checkIn || !booking.checkOut) {
    return;
  }

  bookings.unshift(booking);
  form.reset();
  renderSummary();
  renderBookings();
});

[checkInInput, checkOutInput, document.getElementById('guestName'), document.getElementById('roomType'), document.getElementById('guestCount')].forEach((element) => {
  element.addEventListener('input', renderSummary);
});

renderSummary();
renderBookings();
