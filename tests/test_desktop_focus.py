"""Focusing an uploader must preserve its screenshot geometry."""
import unittest
from unittest.mock import Mock,patch
from tools import desktop

class DesktopFocus(unittest.TestCase):
 def test_visible_maximized_uploader_keeps_its_size(self):
  windows=Mock();windows.IsWindow.return_value=True;windows.IsIconic.return_value=False
  windows.GetForegroundWindow.side_effect=[1,2,2]
  with patch.object(desktop,'desktop_modules',return_value=(Mock(),windows)):
   self.assertIs(desktop.focus(2),windows)
  windows.ShowWindow.assert_not_called()
 def test_minimized_window_is_restored_before_focus(self):
  windows=Mock();windows.IsWindow.return_value=True;windows.IsIconic.return_value=True
  windows.GetForegroundWindow.side_effect=[1,2,2]
  with patch.object(desktop,'desktop_modules',return_value=(Mock(),windows)):
   desktop.focus(2)
  windows.ShowWindow.assert_called_once_with(2,9)

if __name__=='__main__':unittest.main()
