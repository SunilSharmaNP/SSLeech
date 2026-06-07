#!/usr/bin/env python3
from bot import config_dict


class _BotCommands:
    def __init__(self):
        self.reinit()

    def reinit(self):
        suffix = config_dict.get("CMD_SUFFIX", "")
        self.StartCommand = "start"
        self.MirrorCommand = [f"mirror{suffix}", f"m{suffix}"]
        self.QbMirrorCommand = [f"qbmirror{suffix}", f"qm{suffix}"]
        self.YtdlCommand = [f"ytdl{suffix}", f"y{suffix}"]
        self.LeechCommand = [f"leech{suffix}", f"l{suffix}"]
        self.QbLeechCommand = [f"qbleech{suffix}", f"ql{suffix}"]
        self.YtdlLeechCommand = [f"ytdlleech{suffix}", f"yl{suffix}"]
        if config_dict.get("SHOW_EXTRA_CMDS"):
            self.MirrorCommand.extend(
                [
                    f"unzipmirror{suffix}",
                    f"uzm{suffix}",
                    f"zipmirror{suffix}",
                    f"zm{suffix}",
                ]
            )
            self.QbMirrorCommand.extend(
                [
                    f"qbunzipmirror{suffix}",
                    f"quzm{suffix}",
                    f"qbzipmirror{suffix}",
                    f"qzm{suffix}",
                ]
            )
            self.YtdlCommand.extend([f"ytdlzip{suffix}", f"yz{suffix}"])
            self.LeechCommand.extend(
                [
                    f"unzipleech{suffix}",
                    f"uzl{suffix}",
                    f"zipleech{suffix}",
                    f"zl{suffix}",
                ]
            )
            self.QbLeechCommand.extend(
                [
                    f"qbunzipleech{suffix}",
                    f"quzl{suffix}",
                    f"qbzipleech{suffix}",
                    f"qzl{suffix}",
                ]
            )
            self.YtdlLeechCommand.extend(
                [f"ytdlzipleech{suffix}", f"yzl{suffix}"]
            )
        self.CloneCommand = [f"clone{suffix}", f"c{suffix}"]
        self.CountCommand = f"count{suffix}"
        self.DeleteCommand = f"del{suffix}"
        self.CancelMirror = f"cancel{suffix}"
        self.CancelAllCommand = [f"cancelall{suffix}", "cancellallbot"]
        self.ListCommand = f"list{suffix}"
        self.StatusCommand = [f"status{suffix}", f"s{suffix}", "statusall"]
        self.UsersCommand = f"users{suffix}"
        self.AuthorizeCommand = [f"authorize{suffix}", f"a{suffix}"]
        self.UnAuthorizeCommand = [f"unauthorize{suffix}", f"ua{suffix}"]
        self.AddBlackListCommand = [f"blacklist{suffix}", f"bl{suffix}"]
        self.RmBlackListCommand = [f"rmblacklist{suffix}", f"rbl{suffix}"]
        self.AddSudoCommand = f"addsudo{suffix}"
        self.RmSudoCommand = f"rmsudo{suffix}"
        self.PingCommand = [f"ping{suffix}", f"p{suffix}"]
        self.RestartCommand = [f"restart{suffix}", f"r{suffix}", "restartall"]
        self.StatsCommand = [f"stats{suffix}", f"st{suffix}"]
        self.HelpCommand = f"help{suffix}"
        self.LogCommand = f"log{suffix}"
        self.ShellCommand = f"shell{suffix}"
        self.EvalCommand = f"eval{suffix}"
        self.ExecCommand = f"exec{suffix}"
        self.ClearLocalsCommand = f"clearlocals{suffix}"
        self.BotSetCommand = [f"bsetting{suffix}", f"bs{suffix}"]
        self.UserSetCommand = [f"usetting{suffix}", f"us{suffix}"]
        self.BtSelectCommand = f"btsel{suffix}"
        self.CategorySelect = f"ctsel{suffix}"
        self.SpeedCommand = [f"speedtest{suffix}", f"sp{suffix}"]

        self.LoginCommand = "login"
        self.AddImageCommand = f"addimg{suffix}"
        self.ImagesCommand = f"images{suffix}"
        self.AnimeHelpCommand = f"animehelp{suffix}"
        self.MediaInfoCommand = [f"mediainfo{suffix}", f"mi{suffix}"]
        self.MyDramaListCommand = f"mdl{suffix}"
        self.GDCleanCommand = [f"gdclean{suffix}", f"gc{suffix}"]
        self.BroadcastCommand = [f"broadcast{suffix}", f"bc{suffix}"]
        self.SearchCommand = f"search{suffix}"


BotCommands = _BotCommands()
