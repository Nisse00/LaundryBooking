import Button from "react-bootstrap/Button";
import Modal from "react-bootstrap/Modal";

interface BookingPopoutProps {
  show: boolean;
  action: "book" | "cancel";
  text: string;
  onClose: () => void;
  onConfirm: () => void;
}

function BookingPopout({ show, action, text, onClose, onConfirm }: Readonly<BookingPopoutProps>) {
  return (
    <Modal show={show} onHide={onClose}>
      <Modal.Header closeButton>
        <Modal.Title>
          {action === "book" ? "Booking Confirmation" : "Cancellation Booking Confirmation"}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>{text}</Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" onClick={onConfirm}>
          {action === "book" ? "Confirm Booking" : "Confirm Cancellation of Booking"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default BookingPopout;
