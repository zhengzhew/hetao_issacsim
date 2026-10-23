import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from feetech_leader import FeetechReader, read_packet, take_reply
from arm_devices import make_reader
from desheng_leader import DeshengReader


def response(sid, value=2446, status=0, data=True):
    payload=value.to_bytes(2,'little') if data else b''
    body=bytes((sid,len(payload)+2,status))+payload
    return b'\xff\xff'+body+bytes((~sum(body)&255,))


class FeetechTests(unittest.TestCase):
    def test_only_read_model_and_position(self):
        self.assertEqual(read_packet(1).hex(),'ffff0104023802be')
        self.assertEqual(read_packet(1,3,2).hex(),'ffff0104020302f3')
        for args in ((1,40,1),(1,42,2),(254,56,2),(0,56,2),(1,3,1)):
            with self.assertRaises(ValueError):read_packet(*args)

    def test_little_endian_fragmentation_noise_echo_and_checksum(self):
        packet=read_packet(1)
        buffer=bytearray(b'noise'+packet+response(1)[:-1]+b'\x00'+response(2)+response(1)[:4])
        self.assertIsNone(take_reply(buffer,1,packet))
        buffer.extend(response(1)[4:])
        self.assertEqual(take_reply(buffer,1,packet),2446)

    def test_servo_error_is_not_a_position_even_with_short_status(self):
        for data in (True,False):
            with self.assertRaisesRegex(ValueError,'0x02'):
                take_reply(bytearray(response(1,status=2,data=data)),1,read_packet(1))

    def test_wrong_response_length_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'长度'):
            take_reply(bytearray(response(1,data=False)),1)

    def test_reader_dispatch_and_baud_do_not_open_or_toggle_torque(self):
        with patch('serial.Serial') as serial:
            reader=make_reader('feetech-so101','COM-test')
            self.assertIsInstance(reader,FeetechReader)
            self.assertEqual(serial.call_args.kwargs['baudrate'],1000000)
            serial.return_value.open.assert_not_called()
            serial.return_value.write.assert_not_called()
            self.assertFalse(serial.return_value.dtr)
            self.assertFalse(serial.return_value.rts)
            self.assertIsInstance(make_reader('desheng-se-v401','COM-test'),DeshengReader)

    def test_open_validates_all_six_models_and_closes_on_mismatch(self):
        with patch('serial.Serial'):
            reader=FeetechReader('COM-test')
        reader.read=Mock(side_effect=[777]*6)
        reader.open()
        self.assertEqual(reader.models,[777]*6)
        self.assertEqual([call.args for call in reader.read.call_args_list],[(sid,3,2) for sid in range(1,7)])
        reader.read=Mock(side_effect=[777]*5+[123])
        with self.assertRaisesRegex(ValueError,'仅支持'):reader.open()
        reader.port.close.assert_called_once()

    def test_timeout_retries_are_bounded_and_servo_errors_are_fatal(self):
        reader=object.__new__(FeetechReader)
        reader._read_once=Mock(side_effect=[TimeoutError(),2446])
        self.assertEqual(reader.read(1),2446)
        self.assertEqual(reader._read_once.call_count,2)
        reader._read_once=Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):reader.read(1)
        self.assertEqual(reader._read_once.call_count,3)
        reader._read_once=Mock(side_effect=ValueError('servo status'))
        with self.assertRaises(ValueError):reader.read(1)
        self.assertEqual(reader._read_once.call_count,1)

    def test_read_transaction_and_range_validation(self):
        reader=object.__new__(FeetechReader);reader.port=Mock()
        reader.port.in_waiting=8;reader.port.read.return_value=response(1)
        self.assertEqual(reader.read(1),2446)
        reader.port.write.assert_called_once_with(read_packet(1))
        reader.port.read.return_value=response(1,4096)
        with self.assertRaisesRegex(ValueError,'超出范围'):reader.read(1)


if __name__=='__main__':unittest.main()
