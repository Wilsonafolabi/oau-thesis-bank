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

const Screen21AccessRequests = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Access Requests">
      <div className="mb-6 max-w-4xl">
        <p className="text-slate-600">Manage pending requests from users asking to view your embargoed or restricted research.</p>
      </div>
      <div className="space-y-4 max-w-4xl">
        {[
          { name: 'Dr. S. O. Alice', role: 'Faculty', reason: 'Reviewing literature for a related grant proposal.', thesis: 'Economic Impact of Fintech Adoption' },
          { name: 'Tunde Bakare', role: 'Student', reason: 'I am building on your methodology for my master\'s project.', thesis: 'Deep Learning Approaches for Plant Disease' }
        ].map((req, i) => (
          <Card key={i} className="p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <div className="flex items-center space-x-2 mb-1">
                <h4 className="font-semibold text-slate-900 cursor-pointer hover:underline" onClick={() => navigate('researcher-profile')}>{req.name}</h4>
                <Badge variant="gray">{req.role}</Badge>
              </div>
              <p className="text-sm text-[#00502F] font-medium mb-2">Requesting: {req.thesis}</p>
              <p className="text-sm text-slate-600 italic bg-slate-50 p-2 rounded border border-slate-100">"{req.reason}"</p>
            </div>
            <div className="flex space-x-2 w-full md:w-auto">
              <Button variant="ghost" className="text-red-600 hover:bg-red-50 hover:text-red-700 flex-1 md:flex-none">Reject</Button>
              <Button className="flex-1 md:flex-none">Approve Access</Button>
            </div>
          </Card>
        ))}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen21AccessRequests;
