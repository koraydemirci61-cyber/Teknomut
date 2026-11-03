from tkinter import Tk

from sms_robot import SmsRobotApp


def main():
    root = Tk()
    app = SmsRobotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
