import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen42PrivacySettings = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Privacy & Access">
      <div className="max-w-4xl mx-auto flex flex-col md:flex-row gap-8">
        <div className="w-full md:w-64 flex-shrink-0">
          <nav className="space-y-1">
            <button className="w-full flex items-center px-3 py-2 text-slate-600 hover:bg-slate-50 font-medium rounded-md text-sm" onClick={() => navigate('account-settings')}><User className="w-4 h-4 mr-3"/> Profile Info</button>
            <button className="w-full flex items-center px-3 py-2 bg-emerald-50 text-[#00502F] font-medium rounded-md text-sm"><Shield className="w-4 h-4 mr-3"/> Privacy & Access</button>
          </nav>
        </div>
        
        <div className="flex-1 space-y-6">
          <Card className="p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-2">Profile Visibility</h3>
            <p className="text-sm text-slate-500 mb-6">Control who can see your profile in the Researcher Directory.</p>
            
            <div className="space-y-4">
              <label className="flex items-start">
                <input type="radio" name="vis" className="mt-1 mr-3 text-[#00502F]" defaultChecked />
                <div>
                  <span className="block text-sm font-medium text-slate-900">Public (OAU Network Only)</span>
                  <span className="block text-xs text-slate-500">Only logged-in OAU students and staff can view your profile.</span>
                </div>
              </label>
              <label className="flex items-start">
                <input type="radio" name="vis" className="mt-1 mr-3 text-[#00502F]" />
                <div>
                  <span className="block text-sm font-medium text-slate-900">Hidden</span>
                  <span className="block text-xs text-slate-500">Your profile will not appear in directory searches. Your public thesis metadata will still show your name.</span>
                </div>
              </label>
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Communications</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="block text-sm font-medium text-slate-900">Allow direct messages</span>
                  <span className="block text-xs text-slate-500">Other users can send you messages.</span>
                </div>
                <input type="checkbox" className="toggle border-slate-300 text-[#00502F]" defaultChecked />
              </div>
              <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                <div>
                  <span className="block text-sm font-medium text-slate-900">Open to Collaboration Requests</span>
                  <span className="block text-xs text-slate-500">Show a badge on your profile indicating you are open to collaborate.</span>
                </div>
                <input type="checkbox" className="toggle border-slate-300 text-[#00502F]" defaultChecked />
              </div>
            </div>
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen42PrivacySettings;
